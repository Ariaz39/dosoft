#include "scene_guard.hpp"

#include "../platform/windows_game_window.hpp"

#include <obs-frontend-api.h>
#include <obs-module.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <string_view>
#include <thread>
#include <unordered_map>

namespace dofus_scene_guard {

void SceneResolver::replace_bindings(std::vector<SceneBinding> bindings)
{
	bindings_ = std::move(bindings);
}

std::optional<SceneBinding> SceneResolver::resolve(const ActiveGameInstance &instance) const
{
	for (const auto &binding : bindings_) {
		if ((!instance.client_id.empty() && binding.client_id == instance.client_id) ||
		    (instance.hwnd && binding.hwnd == instance.hwnd) ||
		    (!instance.account.empty() && binding.account == instance.account))
			return binding;
	}
	return std::nullopt;
}

namespace {
constexpr auto kCaptureSwitchDelay = std::chrono::milliseconds(25);

void swap_debug(const std::string &message)
{
	static std::mutex mutex;
	std::lock_guard lock(mutex);
	const char *temp = std::getenv("TEMP");
	const std::string path = std::string(temp ? temp : ".") + "\\dofus-scene-guard-swap.log";
	std::ofstream log(path, std::ios::app);
	log << message << '\n';
	blog(LOG_INFO, "[Dofus Scene Guard] %s", message.c_str());
}

void swap_debug_throttled(const std::string &key, const std::string &message)
{
	static std::mutex throttle_mutex;
	static std::unordered_map<std::string, std::chrono::steady_clock::time_point> last_reports;
	const auto now = std::chrono::steady_clock::now();
	{
		std::lock_guard lock(throttle_mutex);
		auto &last = last_reports[key];
		if (last.time_since_epoch().count() && now - last < std::chrono::seconds(5))
			return;
		last = now;
	}
	swap_debug(message);
}

obs_source_t *find_scene(const std::string &name)
{
	obs_source_t *source = obs_get_source_by_name(name.c_str());
	if (source && !obs_scene_from_source(source)) {
		obs_source_release(source);
		return nullptr;
	}
	return source;
}

void migrate_scene_name(const std::string &canonical_name,
			const std::vector<std::string> &legacy_names)
{
	obs_source_t *canonical = find_scene(canonical_name);
	if (canonical) {
		obs_source_release(canonical);
		return;
	}
	for (const auto &legacy_name : legacy_names) {
		obs_source_t *legacy = find_scene(legacy_name);
		if (!legacy)
			continue;
		obs_source_set_name(legacy, canonical_name.c_str());
		obs_source_release(legacy);
		swap_debug("SETUP_RENAME scene=" + legacy_name + " -> " + canonical_name);
		return;
	}
}

std::string capture_state(obs_source_t *source)
{
	if (!source)
		return "missing";
	return "name=" + std::string(obs_source_get_name(source)) +
	       " width=" + std::to_string(obs_source_get_width(source)) +
	       " height=" + std::to_string(obs_source_get_height(source)) +
	       " showing=" + (obs_source_showing(source) ? "true" : "false");
}

bool capture_ready(obs_sceneitem_t *item)
{
	obs_source_t *source = obs_sceneitem_get_source(item);
	return source && obs_source_get_width(source) > 0 && obs_source_get_height(source) > 0;
}

bool nearly_equal(float left, float right, float tolerance = 0.01f)
{
	return std::fabs(left - right) <= tolerance;
}

bool empty_crop(const obs_sceneitem_crop &crop)
{
	return crop.left == 0 && crop.top == 0 && crop.right == 0 && crop.bottom == 0;
}

bool unity_layout_can_be_auto_fitted(const obs_transform_info &transform,
				     const obs_sceneitem_crop &crop)
{
	if (!empty_crop(crop) || transform.bounds_type != OBS_BOUNDS_NONE ||
	    !nearly_equal(transform.rot, 0.0f) || !nearly_equal(transform.pos.x, 0.0f, 1.0f) ||
	    !nearly_equal(transform.pos.y, 0.0f, 1.0f))
		return false;

	const bool finite_scale = std::isfinite(transform.scale.x) && std::isfinite(transform.scale.y);
	const bool untouched_scale = nearly_equal(transform.scale.x, 1.0f) &&
				     nearly_equal(transform.scale.y, 1.0f);
	const bool pathological_scale = !finite_scale || std::fabs(transform.scale.x) >= 2.0f ||
					 std::fabs(transform.scale.y) >= 2.0f ||
					 nearly_equal(transform.scale.x, 0.0f) ||
					 nearly_equal(transform.scale.y, 0.0f);
	return untouched_scale || pathological_scale;
}

bool auto_fit_unity_capture(obs_sceneitem_t *item, const std::string &capture_name)
{
	if (!item)
		return false;
	obs_video_info video{};
	if (!obs_get_video_info(&video) || !video.base_width || !video.base_height)
		return false;

	obs_transform_info transform{};
	obs_sceneitem_crop crop{};
	obs_sceneitem_get_info2(item, &transform);
	obs_sceneitem_get_crop(item, &crop);
	if (!unity_layout_can_be_auto_fitted(transform, crop))
		return false;

	// Bounds scale dynamically when the Unity client changes resolution. This
	// avoids the 200/300% crop produced by a native 4K game source on a 1080p
	// OBS canvas while preserving the complete image and its aspect ratio.
	transform.pos.x = static_cast<float>(video.base_width) / 2.0f;
	transform.pos.y = static_cast<float>(video.base_height) / 2.0f;
	transform.rot = 0.0f;
	transform.scale.x = 1.0f;
	transform.scale.y = 1.0f;
	transform.alignment = OBS_ALIGN_CENTER;
	transform.bounds_type = OBS_BOUNDS_SCALE_INNER;
	transform.bounds_alignment = OBS_ALIGN_CENTER;
	transform.bounds.x = static_cast<float>(video.base_width);
	transform.bounds.y = static_cast<float>(video.base_height);
	obs_sceneitem_set_info2(item, &transform);
	swap_debug("UNITY_AUTO_FIT capture=" + capture_name + " canvas=" +
		   std::to_string(video.base_width) + "x" + std::to_string(video.base_height));
	return true;
}

struct ManagedCaptureContext {
	std::string prefix;
	std::vector<obs_sceneitem_t *> items;
};

struct MatchingManagedCaptureContext {
	std::string prefix;
	std::string source_id;
	std::string target_window;
	std::vector<obs_sceneitem_t *> items;
};

struct SourceReferenceContext {
	obs_source_t *target = nullptr;
	bool found = false;
};

bool find_source_reference(obs_scene_t *, obs_sceneitem_t *item, void *opaque)
{
	auto *context = static_cast<SourceReferenceContext *>(opaque);
	if (obs_sceneitem_get_source(item) == context->target) {
		context->found = true;
		return false;
	}
	return true;
}

bool source_is_in_scene(void *opaque, obs_source_t *scene_source)
{
	auto *context = static_cast<SourceReferenceContext *>(opaque);
	obs_scene_t *scene = obs_scene_from_source(scene_source);
	if (scene)
		obs_scene_enum_items(scene, find_source_reference, context);
	return !context->found;
}

bool source_has_scene_reference(obs_source_t *source)
{
	SourceReferenceContext context{source, false};
	obs_enum_scenes(source_is_in_scene, &context);
	return context.found;
}

bool generated_scene_duplicate(const std::string &name, const std::string &canonical_name)
{
	if (!name.starts_with(canonical_name) || name.size() == canonical_name.size())
		return false;
	std::string_view suffix{name.data() + canonical_name.size(),
				name.size() - canonical_name.size()};
	while (suffix.starts_with(" 2"))
		suffix.remove_prefix(2);
	return suffix.empty();
}

struct DuplicateSceneContext {
	std::string canonical_name;
	std::vector<obs_source_t *> sources;
};

bool collect_generated_scene_duplicate(void *opaque, obs_source_t *source)
{
	auto *context = static_cast<DuplicateSceneContext *>(opaque);
	const char *name = obs_source_get_name(source);
	if (name && generated_scene_duplicate(name, context->canonical_name))
		context->sources.push_back(obs_source_get_ref(source));
	return true;
}

struct MergeSceneContext {
	obs_scene_t *canonical = nullptr;
	size_t merged = 0;
};

bool merge_scene_item(obs_scene_t *, obs_sceneitem_t *item, void *opaque)
{
	auto *context = static_cast<MergeSceneContext *>(opaque);
	obs_source_t *source = obs_sceneitem_get_source(item);
	const char *name = source ? obs_source_get_name(source) : nullptr;
	if (!source || !name || obs_scene_find_source(context->canonical, name))
		return true;
	obs_sceneitem_t *copy = obs_scene_add(context->canonical, source);
	if (!copy)
		return true;
	obs_transform_info transform{};
	obs_sceneitem_crop crop{};
	obs_sceneitem_get_info2(item, &transform);
	obs_sceneitem_get_crop(item, &crop);
	obs_sceneitem_set_info2(copy, &transform);
	obs_sceneitem_set_crop(copy, &crop);
	obs_sceneitem_set_visible(copy, obs_sceneitem_visible(item));
	obs_sceneitem_set_locked(copy, obs_sceneitem_locked(item));
	++context->merged;
	return true;
}

struct ReplaceSceneReferenceContext {
	obs_source_t *duplicate = nullptr;
	obs_source_t *canonical = nullptr;
	size_t replaced = 0;
};

bool replace_scene_reference_item(obs_scene_t *scene, obs_sceneitem_t *item, void *opaque)
{
	auto *context = static_cast<ReplaceSceneReferenceContext *>(opaque);
	if (obs_sceneitem_get_source(item) != context->duplicate)
		return true;

	const char *canonical_name = obs_source_get_name(context->canonical);
	if (!canonical_name || !obs_scene_find_source(scene, canonical_name)) {
		obs_sceneitem_t *copy = obs_scene_add(scene, context->canonical);
		if (copy) {
			obs_transform_info transform{};
			obs_sceneitem_crop crop{};
			obs_sceneitem_get_info2(item, &transform);
			obs_sceneitem_get_crop(item, &crop);
			obs_sceneitem_set_info2(copy, &transform);
			obs_sceneitem_set_crop(copy, &crop);
			obs_sceneitem_set_visible(copy, obs_sceneitem_visible(item));
			obs_sceneitem_set_locked(copy, obs_sceneitem_locked(item));
		}
	}

	obs_sceneitem_remove(item);
	++context->replaced;
	return true;
}

bool replace_scene_references(void *opaque, obs_source_t *scene_source)
{
	auto *context = static_cast<ReplaceSceneReferenceContext *>(opaque);
	if (scene_source == context->duplicate)
		return true;
	obs_scene_t *scene = obs_scene_from_source(scene_source);
	if (scene)
		obs_scene_enum_items(scene, replace_scene_reference_item, context);
	return true;
}

struct SweepDuplicateReferenceContext {
	obs_source_t *canonical = nullptr;
	std::string canonical_name;
	size_t removed = 0;
	bool parent_is_canonical = false;
};

bool sweep_duplicate_reference_item(obs_scene_t *scene, obs_sceneitem_t *item, void *opaque)
{
	auto *context = static_cast<SweepDuplicateReferenceContext *>(opaque);
	obs_source_t *source = obs_sceneitem_get_source(item);
	const char *name = source ? obs_source_get_name(source) : nullptr;
	if (!name || !generated_scene_duplicate(name, context->canonical_name))
		return true;

	if (!context->parent_is_canonical &&
	    !obs_scene_find_source(scene, context->canonical_name.c_str())) {
		obs_sceneitem_t *copy = obs_scene_add(scene, context->canonical);
		if (copy) {
			obs_transform_info transform{};
			obs_sceneitem_crop crop{};
			obs_sceneitem_get_info2(item, &transform);
			obs_sceneitem_get_crop(item, &crop);
			obs_sceneitem_set_info2(copy, &transform);
			obs_sceneitem_set_crop(copy, &crop);
			obs_sceneitem_set_visible(copy, obs_sceneitem_visible(item));
			obs_sceneitem_set_locked(copy, obs_sceneitem_locked(item));
		}
	}

	obs_sceneitem_remove(item);
	++context->removed;
	return true;
}

bool sweep_duplicate_references(void *opaque, obs_source_t *scene_source)
{
	auto *context = static_cast<SweepDuplicateReferenceContext *>(opaque);
	obs_scene_t *scene = obs_scene_from_source(scene_source);
	if (!scene)
		return true;
	context->parent_is_canonical = scene_source == context->canonical;
	obs_scene_enum_items(scene, sweep_duplicate_reference_item, context);
	return true;
}

struct CompetingCaptureContext {
	std::string target_window;
	std::string managed_name;
	std::vector<obs_source_t *> candidates;
};

bool collect_competing_capture(void *opaque, obs_source_t *source)
{
	auto *context = static_cast<CompetingCaptureContext *>(opaque);
	const char *source_id = obs_source_get_id(source);
	const char *name = obs_source_get_name(source);
	if (!source_id || std::string(source_id) != "game_capture" || !name ||
	    context->managed_name == name)
		return true;
	obs_data_t *settings = obs_source_get_settings(source);
	const std::string window = obs_data_get_string(settings, "window");
	obs_data_release(settings);
	if (window == context->target_window)
		context->candidates.push_back(obs_source_get_ref(source));
	return true;
}

void retire_orphaned_competing_captures(const std::string &target_window,
					const std::string &managed_name)
{
	CompetingCaptureContext context{target_window, managed_name, {}};
	obs_enum_all_sources(collect_competing_capture, &context);
	for (obs_source_t *candidate : context.candidates) {
		const std::string name = obs_source_get_name(candidate);
		if (!source_has_scene_reference(candidate)) {
			swap_debug("SYNC_RETIRE orphan competing capture=" + name +
				   " target=" + target_window);
			obs_source_remove(candidate);
		} else {
			swap_debug_throttled("capture-conflict-" + name,
					     "SYNC_CONFLICT another scene uses capture=" + name +
					     " for the same game window");
		}
		obs_source_release(candidate);
	}
}

bool collect_managed_capture(obs_scene_t *, obs_sceneitem_t *item, void *opaque)
{
	auto *context = static_cast<ManagedCaptureContext *>(opaque);
	obs_source_t *source = obs_sceneitem_get_source(item);
	const char *name = source ? obs_source_get_name(source) : nullptr;
	if (name && std::string_view(name).starts_with(context->prefix))
		context->items.push_back(item);
	return true;
}

bool collect_matching_managed_capture(obs_scene_t *, obs_sceneitem_t *item, void *opaque)
{
	auto *context = static_cast<MatchingManagedCaptureContext *>(opaque);
	obs_source_t *source = obs_sceneitem_get_source(item);
	const char *name = source ? obs_source_get_name(source) : nullptr;
	const char *source_id = source ? obs_source_get_id(source) : nullptr;
	if (!name || !source_id || !std::string_view(name).starts_with(context->prefix) ||
	    (!context->source_id.empty() && context->source_id != source_id))
		return true;
	obs_data_t *settings = obs_source_get_settings(source);
	const std::string window = obs_data_get_string(settings, "window");
	obs_data_release(settings);
	if (window == context->target_window)
		context->items.push_back(item);
	return true;
}
}

void SceneGuard::apply_config(const GuardConfig &config)
{
	config_ = config;
	if (config_.game_scene.empty())
		config_.game_scene = "DOSOFT — Dofus";
	if (config_.stream_scene.empty())
		config_.stream_scene = "Stream";
	if (config_.capture_prefix.empty())
		config_.capture_prefix = "DOSOFT Dofus — ";
	if (config_.engine.empty())
		config_.engine = "unity";
	config_.maximum_captures = std::max<size_t>(1, config_.maximum_captures);
	config_.fallback_delay = std::max(std::chrono::milliseconds(250), config_.fallback_delay);
}

std::string SceneGuard::capture_name_for(const ActiveGameInstance &account) const
{
	// A PID/HWND identity changes whenever the game restarts.  That previously
	// left an active game-capture source behind, which kept OBS' hook while a
	// newly created source retried init_pipe forever.  The DOSOFT account label
	// is stable across game restarts and therefore makes the capture reusable.
	const std::string identity = !account.account.empty()
				     ? account.account
				     : (!account.client_id.empty() ? account.client_id
							   : std::to_string(account.hwnd));
	return config_.capture_prefix + identity;
}

void SceneGuard::prewarm_capture(obs_source_t *capture, const std::string &capture_name)
{
	auto existing = prewarmed_captures_.find(capture_name);
	if (existing != prewarmed_captures_.end()) {
		obs_source_t *warmed_capture = obs_weak_source_get_source(existing->second);
		const bool same_capture = warmed_capture == capture;
		if (warmed_capture)
			obs_source_release(warmed_capture);
		if (same_capture && obs_source_active(capture))
			return;
		obs_weak_source_release(existing->second);
		prewarmed_captures_.erase(existing);
	}
	obs_source_inc_active(capture);
	prewarmed_captures_.emplace(capture_name, obs_source_get_weak_source(capture));
	swap_debug("SYNC_PREWARM capture=" + capture_name + " " + capture_state(capture));
}

void SceneGuard::release_prewarm(const std::string &capture_name)
{
	auto existing = prewarmed_captures_.find(capture_name);
	if (existing == prewarmed_captures_.end())
		return;
	obs_source_t *capture = obs_weak_source_get_source(existing->second);
	if (capture) {
		obs_source_dec_active(capture);
		obs_source_release(capture);
	}
	obs_weak_source_release(existing->second);
	prewarmed_captures_.erase(existing);
}

size_t SceneGuard::managed_capture_count()
{
	obs_source_t *scene_source = find_scene(config_.game_scene);
	if (!scene_source)
		return 0;
	ManagedCaptureContext context{config_.capture_prefix, {}};
	obs_scene_enum_items(obs_scene_from_source(scene_source), collect_managed_capture, &context);
	obs_source_release(scene_source);
	return context.items.size();
}

void SceneGuard::clear_game_captures(const char *reason)
{
	obs_source_t *scene_source = find_scene(config_.game_scene);
	if (!scene_source)
		return;
	ManagedCaptureContext context{config_.capture_prefix, {}};
	obs_scene_enum_items(obs_scene_from_source(scene_source), collect_managed_capture, &context);
	for (obs_sceneitem_t *item : context.items) {
		obs_source_t *source = obs_sceneitem_get_source(item);
		const std::string name = source ? obs_source_get_name(source) : "";
		if (!name.empty())
			release_prewarm(name);
		obs_sceneitem_remove(item);
	}
	obs_source_release(scene_source);
	resolver_.replace_bindings({});
	last_selected_client_id_.clear();
	swap_debug(std::string("CAPTURE_RESET reason=") + reason + " removed=" + std::to_string(context.items.size()));
}

bool SceneGuard::ensure_capture_in_game_scene(const ActiveGameInstance &account)
{
	const std::string capture_name = capture_name_for(account);
	const std::string target_window = game_capture_window_id(account.hwnd);
	const bool retro = account.engine == "retro" || account.engine == "rétro" || account.engine == "Rétro";
	const bool wakfu = account.engine == "wakfu" || account.engine == "Wakfu";
	const bool uses_window_capture = retro || wakfu;
	obs_source_t *scene_source = find_scene(config_.game_scene);
	if (!scene_source) {
		swap_debug("SYNC_ERROR game scene missing=" + config_.game_scene);
		return false;
	}
	obs_scene_t *game_scene = obs_scene_from_source(scene_source);
	obs_source_t *capture = obs_get_source_by_name(capture_name.c_str());
	const char *source_id = uses_window_capture ? "window_capture" : "game_capture";
	obs_sceneitem_t *canonical_item = capture ? obs_scene_find_source(game_scene, capture_name.c_str()) : nullptr;
	obs_transform_info migrated_transform{};
	obs_sceneitem_crop migrated_crop{};
	bool migrated_layout = false;
	bool migrated_visible = false;
	auto remember_layout = [&](obs_sceneitem_t *item) {
		if (!item || migrated_layout)
			return;
		obs_sceneitem_get_info2(item, &migrated_transform);
		obs_sceneitem_get_crop(item, &migrated_crop);
		migrated_visible = obs_sceneitem_visible(item);
		migrated_layout = true;
	};

	// Wakfu used to be created as game_capture. Replace that Java/OpenGL hook
	// with Windows Graphics Capture while preserving the user's scene layout.
	if (capture) {
		const char *existing_id = obs_source_get_id(capture);
		if (!existing_id || std::string(existing_id) != source_id) {
			remember_layout(canonical_item);
			release_prewarm(capture_name);
			if (canonical_item)
				obs_sceneitem_remove(canonical_item);
			obs_source_remove(capture);
			obs_source_release(capture);
			capture = nullptr;
			canonical_item = nullptr;
			swap_debug("SYNC_CONVERT capture=" + capture_name + " -> " + source_id);
		}
	}

	// Adopt a legacy PID-based source that already captures this exact window.
	// Prefer the visible item: it is the one the streamer has positioned and it
	// is also the most likely owner of the currently healthy OBS game hook.
	MatchingManagedCaptureContext matches{config_.capture_prefix, "", target_window, {}};
	obs_scene_enum_items(game_scene, collect_matching_managed_capture, &matches);
	if (!capture) {
		// A character can change inside the same game process. Reuse the source
		// already bound to that DOSOFT client/HWND, even though its old window
		// title no longer matches, then retarget it below.
		for (const auto &binding : resolver_.bindings()) {
			const bool same_client = !account.client_id.empty() && binding.client_id == account.client_id;
			const bool same_window = account.hwnd && binding.hwnd == account.hwnd;
			if (!same_client && !same_window)
				continue;
			obs_source_t *bound_capture = obs_get_source_by_name(binding.capture_name.c_str());
			if (!bound_capture)
				continue;
			const char *bound_id = obs_source_get_id(bound_capture);
			obs_sceneitem_t *bound_item = obs_scene_find_source(game_scene, binding.capture_name.c_str());
			if (!bound_id || source_id != std::string(bound_id) || !bound_item) {
				obs_source_release(bound_capture);
				continue;
			}
			const std::string previous_name = obs_source_get_name(bound_capture);
			release_prewarm(previous_name);
			obs_source_set_name(bound_capture, capture_name.c_str());
			capture = bound_capture;
			canonical_item = bound_item;
			swap_debug("SYNC_REUSE client=" + account.client_id + " capture=" +
				   previous_name + " -> " + capture_name);
			break;
		}
	}
	if (!capture && !matches.items.empty()) {
		const auto compatible = [&](obs_sceneitem_t *item) {
			obs_source_t *source = obs_sceneitem_get_source(item);
			const char *id = source ? obs_source_get_id(source) : nullptr;
			return id && std::string(id) == source_id;
		};
		const auto visible = std::find_if(matches.items.begin(), matches.items.end(), [&](obs_sceneitem_t *item) {
			return compatible(item) && obs_sceneitem_visible(item);
		});
		const auto first_compatible = std::find_if(matches.items.begin(), matches.items.end(), compatible);
		const auto visible_any = std::find_if(matches.items.begin(), matches.items.end(), [](obs_sceneitem_t *item) {
			return obs_sceneitem_visible(item);
		});
		obs_sceneitem_t *layout_donor = visible != matches.items.end()
						 ? *visible
						 : (first_compatible != matches.items.end() ? *first_compatible
											 : (visible_any != matches.items.end()
													? *visible_any
													: matches.items.front()));
		remember_layout(layout_donor);
		canonical_item = visible != matches.items.end()
				 ? *visible
				 : (first_compatible != matches.items.end() ? *first_compatible : nullptr);
		if (canonical_item)
			capture = obs_source_get_ref(obs_sceneitem_get_source(canonical_item));
	}
	if (capture && canonical_item && std::string(obs_source_get_name(capture)) != capture_name) {
		const std::string legacy_name = obs_source_get_name(capture);
		release_prewarm(legacy_name);
		obs_source_set_name(capture, capture_name.c_str());
		swap_debug("SYNC_ADOPT capture=" + legacy_name + " -> " + capture_name +
			   " target=" + target_window);
	}

	// Consolidate duplicates owned by DOSOFT.  If an older visible duplicate
	// exists while the stable source already exists, inherit its transform and
	// visibility before retiring it so a migration never loses the crop.
	for (obs_sceneitem_t *item : matches.items) {
		if (item == canonical_item)
			continue;
		obs_source_t *duplicate = obs_sceneitem_get_source(item);
		if (!duplicate || duplicate == capture)
			continue;
		if (canonical_item && obs_sceneitem_visible(item) && !obs_sceneitem_visible(canonical_item)) {
			obs_transform_info transform{};
			obs_sceneitem_crop crop{};
			obs_sceneitem_get_info2(item, &transform);
			obs_sceneitem_get_crop(item, &crop);
			obs_sceneitem_set_info2(canonical_item, &transform);
			obs_sceneitem_set_crop(canonical_item, &crop);
			obs_sceneitem_set_visible(canonical_item, true);
		}
		const std::string duplicate_name = obs_source_get_name(duplicate);
		obs_source_t *duplicate_ref = obs_source_get_ref(duplicate);
		release_prewarm(duplicate_name);
		obs_sceneitem_remove(item);
		if (!source_has_scene_reference(duplicate_ref))
			obs_source_remove(duplicate_ref);
		obs_source_release(duplicate_ref);
		swap_debug("SYNC_RETIRE duplicate managed capture=" + duplicate_name +
			   " canonical=" + capture_name);
	}

	if (!uses_window_capture)
		retire_orphaned_competing_captures(target_window, capture_name);
	if (!capture) {
		obs_data_t *settings = obs_data_create();
		obs_data_set_string(settings, "window", target_window.c_str());
		obs_data_set_int(settings, "priority", 1);
		if (uses_window_capture) {
			// Dofus Retro is Chromium-based. OBS' game hook cannot attach to it,
			// and Wakfu's Java/OpenGL hook is extremely choppy. Windows Graphics
			// Capture supports both windows without injecting into their process.
			obs_data_set_int(settings, "method", 2);
			obs_data_set_bool(settings, "cursor", true);
			obs_data_set_bool(settings, "client_area", true);
			obs_data_set_bool(settings, "force_sdr", false);
		} else {
			obs_data_set_string(settings, "capture_mode", "window");
			obs_data_set_bool(settings, "capture_cursor", true);
		}
		capture = obs_source_create(source_id, capture_name.c_str(), settings, nullptr);
		obs_data_release(settings);
		if (!capture) {
			swap_debug("SYNC_ERROR capture creation failed client=" + account.client_id);
			obs_source_release(scene_source);
			return false;
		}
		obs_sceneitem_t *item = obs_scene_add(game_scene, capture);
		if (item) {
			if (migrated_layout) {
				obs_sceneitem_set_info2(item, &migrated_transform);
				obs_sceneitem_set_crop(item, &migrated_crop);
			}
			obs_sceneitem_set_visible(item, migrated_layout ? migrated_visible : false);
		}
	} else {
		const char *existing_id = obs_source_get_id(capture);
		if (!existing_id || std::string(existing_id) != source_id) {
			swap_debug("SYNC_ERROR wrong capture type name=" + capture_name +
				   " expected=" + source_id);
			obs_source_release(capture);
			obs_source_release(scene_source);
			return false;
		}
		obs_data_t *settings = obs_source_get_settings(capture);
		obs_data_set_string(settings, "window", target_window.c_str());
		obs_data_set_int(settings, "priority", 1);
		if (uses_window_capture) {
			obs_data_set_int(settings, "method", 2);
			obs_data_set_bool(settings, "cursor", true);
			obs_data_set_bool(settings, "client_area", true);
		} else {
			obs_data_set_string(settings, "capture_mode", "window");
			obs_data_set_bool(settings, "capture_cursor", true);
		}
		obs_source_update(capture, settings);
		obs_data_release(settings);
		if (!obs_scene_find_source(game_scene, capture_name.c_str())) {
			obs_sceneitem_t *item = obs_scene_add(game_scene, capture);
			if (item)
				obs_sceneitem_set_visible(item, false);
		}
	}
	if (!uses_window_capture) {
		obs_sceneitem_t *unity_item = obs_scene_find_source(game_scene, capture_name.c_str());
		auto_fit_unity_capture(unity_item, capture_name);
	}
	prewarm_capture(capture, capture_name);
	swap_debug("SYNC_CAPTURE client=" + account.client_id + " account=" + account.account);
	obs_source_release(capture);
	obs_source_release(scene_source);
	return true;
}

bool SceneGuard::update_capture_target(obs_sceneitem_t *item, const ActiveGameInstance &account)
{
	obs_source_t *capture = obs_sceneitem_get_source(item);
	if (!capture)
		return false;
	obs_data_t *settings = obs_source_get_settings(capture);
	const std::string target_window = game_capture_window_id(account.hwnd);
	const std::string current_window = obs_data_get_string(settings, "window");
	obs_data_set_string(settings, "window", target_window.c_str());
	obs_data_set_int(settings, "priority", 1);
	const char *source_id = obs_source_get_id(capture);
	if (source_id && std::string(source_id) == "window_capture") {
		obs_data_set_int(settings, "method", 2);
		obs_data_set_bool(settings, "cursor", true);
		obs_data_set_bool(settings, "client_area", true);
	} else {
		obs_data_set_string(settings, "capture_mode", "window");
		obs_data_set_bool(settings, "capture_cursor", true);
	}
	obs_source_update(capture, settings);
	obs_data_release(settings);
	if (current_window != target_window)
		swap_debug("CAPTURE_RETARGET client=" + account.client_id + " account=" + account.account);
	return true;
}

bool SceneGuard::show_only_capture(const SceneBinding &binding, const ActiveGameInstance &account)
{
	obs_source_t *scene_source = find_scene(config_.game_scene);
	if (!scene_source) {
		// A missing managed scene means the connector is no longer armed. Stop
		// polling immediately: a later successful synchronization explicitly
		// re-enables auto-swap through the pipe action.
		team_synchronized_ = false;
		auto_swap_enabled_ = false;
		fallback_timer_running_ = false;
		swap_debug_throttled("missing-game-scene",
				     "SWAP_ERROR game scene missing=" + config_.game_scene +
				     "; auto-swap disabled until synchronization");
		return false;
	}
	obs_scene_t *game_scene = obs_scene_from_source(scene_source);
	obs_sceneitem_t *selected_item = obs_scene_find_source(game_scene, binding.capture_name.c_str());
	if (!selected_item) {
		obs_source_release(scene_source);
		swap_debug("SWAP_WAIT capture missing=" + binding.capture_name);
		return false;
	}
	update_capture_target(selected_item, account);
	if (!capture_ready(selected_item)) {
		swap_debug_throttled("show-wait-" + binding.client_id,
				     "SHOW_WAIT client=" + binding.client_id + " " +
				     capture_state(obs_sceneitem_get_source(selected_item)));
		obs_source_release(scene_source);
		return false;
	}
	std::vector<obs_sceneitem_t *> previous_visible_items;
	for (const auto &candidate : resolver_.bindings()) {
		if (candidate.capture_name == binding.capture_name)
			continue;
		obs_sceneitem_t *item = obs_scene_find_source(game_scene, candidate.capture_name.c_str());
		if (item && obs_sceneitem_visible(item))
			previous_visible_items.push_back(item);
	}
	if (!obs_sceneitem_visible(selected_item)) {
		obs_sceneitem_set_order(selected_item, OBS_ORDER_MOVE_BOTTOM);
		obs_sceneitem_set_visible(selected_item, true);
		swap_debug("SHOW client=" + binding.client_id + " " + capture_state(obs_sceneitem_get_source(selected_item)));
		if (!previous_visible_items.empty())
			std::this_thread::sleep_for(kCaptureSwitchDelay);
	}
	for (obs_sceneitem_t *item : previous_visible_items) {
		swap_debug("HIDE " + capture_state(obs_sceneitem_get_source(item)));
		obs_sceneitem_set_visible(item, false);
	}
	obs_source_release(scene_source);
	swap_debug("SWAP_OK client=" + binding.client_id + " account=" + account.account);
	return true;
}

bool SceneGuard::synchronize_team(const std::vector<ActiveGameInstance> &accounts,
				  const GuardConfig &config, std::uint64_t revision)
{
	if (revision && revision < latest_revision_) {
		swap_debug("SYNC_IGNORED stale revision=" + std::to_string(revision));
		return true;
	}
	latest_revision_ = std::max(latest_revision_, revision);
	apply_config(config);
	if (accounts.empty()) {
		swap_debug("SYNC_WAIT no ready account; keeping previous bindings");
		return false;
	}
	if (managed_capture_count() > config_.maximum_captures)
		clear_game_captures("configured capture limit exceeded");
	std::vector<SceneBinding> bindings;
	bindings.reserve(accounts.size());
	for (const auto &account : accounts) {
		if (account.account.empty() || !account.hwnd || !ensure_capture_in_game_scene(account))
			continue;
		bindings.push_back({account.client_id, account.account, account.hwnd, capture_name_for(account),
				    account.engine.empty() ? config_.engine : account.engine});
	}
	if (bindings.empty()) {
		swap_debug("SYNC_WAIT no capture could be prepared; keeping previous bindings");
		return false;
	}
	resolver_.replace_bindings(std::move(bindings));
	team_synchronized_ = true;
	fallback_timer_running_ = false;
	swap_debug("SYNC_OK accounts=" + std::to_string(resolver_.bindings().size()) +
		   " revision=" + std::to_string(revision));
	return true;
}

bool SceneGuard::rebuild_team(const std::vector<ActiveGameInstance> &accounts,
			      const GuardConfig &config, std::uint64_t revision)
{
	// The user may have deleted the managed scene directly in OBS. Rebuild is
	// an emergency/self-healing action, so it must not depend exclusively on a
	// preceding setup request from DOSOFT to recreate the container.
	if (!setup_scenes(config, {})) {
		swap_debug("REBUILD_ERROR unable to restore game scene=" + config.game_scene);
		return false;
	}
	clear_game_captures("manual rebuild requested by DOSOFT");
	const bool ok = synchronize_team(accounts, config, revision);
	if (ok)
		obs_frontend_save();
	return ok;
}

void SceneGuard::set_auto_swap(bool enabled)
{
	auto_swap_enabled_ = enabled;
	if (!enabled) {
		fallback_timer_running_ = false;
		last_selected_client_id_.clear();
	}
	swap_debug(std::string("AUTO_SWAP ") + (enabled ? "enabled" : "disabled"));
}

ControlResult SceneGuard::control_state(const std::string &command, const std::string &source,
					const std::string &scene)
{
	if (command == "toggle_microphone") {
		obs_source_t *mic = obs_get_source_by_name(source.c_str());
		if (!mic) { swap_debug("CONTROL_ERROR microphone missing=" + source); return {}; }
		const bool muted = obs_source_muted(mic);
		obs_source_release(mic);
		return {true, true, muted};
	}
	if (command == "toggle_camera" || command == "toggle_source") {
		obs_source_t *container = find_scene(scene);
		if (!container) { swap_debug("CONTROL_ERROR scene missing=" + scene); return {}; }
		obs_sceneitem_t *item = obs_scene_find_source(obs_scene_from_source(container), source.c_str());
		ControlResult result;
		if (item) {
			result = {true, true, !obs_sceneitem_visible(item)};
		} else {
			swap_debug("CONTROL_ERROR source missing=" + source);
		}
		obs_source_release(container);
		return result;
	}
	if (command == "toggle_pause" || command == "toggle_scene") {
		obs_source_t *target = find_scene(scene);
		if (!target)
			return {};
		obs_source_release(target);
		obs_source_t *current = obs_frontend_get_current_scene();
		const bool selected = current && std::string(obs_source_get_name(current)) == scene;
		if (current)
			obs_source_release(current);
		return {true, true, selected};
	}
	if (command == "switch_scene") {
		obs_source_t *target = find_scene(scene);
		if (!target)
			return {};
		obs_source_release(target);
		return {true, false, false};
	}
	swap_debug("CONTROL_ERROR unknown command=" + command);
	return {};
}

ControlResult SceneGuard::control(const std::string &command, const std::string &source,
				  const std::string &scene)
{
	if (command == "toggle_microphone") {
		ControlResult before = control_state(command, source, scene);
		if (!before.ok)
			return before;
		obs_source_t *mic = obs_get_source_by_name(source.c_str());
		if (!mic)
			return {};
		obs_source_set_muted(mic, !obs_source_muted(mic));
		obs_source_release(mic);
		return control_state(command, source, scene);
	}
	if (command == "toggle_camera" || command == "toggle_source") {
		obs_source_t *container = find_scene(scene);
		if (!container) { swap_debug("CONTROL_ERROR scene missing=" + scene); return {}; }
		obs_sceneitem_t *item = obs_scene_find_source(obs_scene_from_source(container), source.c_str());
		if (item)
			obs_sceneitem_set_visible(item, !obs_sceneitem_visible(item));
		else
			swap_debug("CONTROL_ERROR source missing=" + source);
		obs_source_release(container);
		return item ? control_state(command, source, scene) : ControlResult{};
	}
	if (command == "toggle_pause" || command == "toggle_scene") {
		ControlResult before = control_state(command, source, scene);
		if (!before.ok)
			return before;
		if (!switch_to_scene(before.off ? config_.stream_scene : scene))
			return {};
		return control_state(command, source, scene);
	}
	if (command == "switch_scene")
		return {switch_to_scene(scene), false, false};
	swap_debug("CONTROL_ERROR unknown command=" + command);
	return {};
}

bool SceneGuard::switch_to_scene(const std::string &scene_name)
{
	obs_source_t *scene = find_scene(scene_name);
	if (!scene) {
		swap_debug("SWAP_ERROR scene missing=" + scene_name);
		return false;
	}
	obs_frontend_set_current_scene(scene);
	obs_source_release(scene);
	swap_debug("SWAP_SCENE scene=" + scene_name);
	return true;
}

void SceneGuard::restore_after_recovery()
{
	if (!full_cam_active_)
		return;
	obs_source_t *current = obs_frontend_get_current_scene();
	const bool still_on_fallback = current && std::string(obs_source_get_name(current)) == config_.fallback_scene;
	if (current)
		obs_source_release(current);
	if (still_on_fallback)
		switch_to_scene(config_.stream_scene);
	else
		swap_debug("RECOVERY no scene change: user left the fallback scene manually");
	full_cam_active_ = false;
}

bool SceneGuard::select_account(const ActiveGameInstance &account)
{
	if (!auto_swap_enabled_)
		return false;
	const auto binding = resolver_.resolve(account);
	if (!binding) {
		swap_debug_throttled("unsynchronized-" + account.client_id,
				     "SWAP_WAIT unsynchronized client=" + account.client_id +
				     " account=" + account.account);
		return false;
	}
	if (binding->client_id == last_selected_client_id_)
		return true;
	if (!show_only_capture(*binding, account))
		return false;
	last_selected_client_id_ = binding->client_id;
	fallback_timer_running_ = false;
	restore_after_recovery();
	return true;
}

bool SceneGuard::all_bound_windows_closed() const
{
	return !resolver_.bindings().empty() && !has_any_dofus_window(resolver_.bindings());
}

void SceneGuard::poll_foreground_window()
{
	if (!auto_swap_enabled_)
		return;
	const auto account = foreground_dofus_window(config_.engine);
	if (account) {
		fallback_timer_running_ = false;
		select_account(*account);
		return;
	}
	if (!team_synchronized_ || !config_.fallback_enabled || config_.fallback_scene.empty() ||
	    !all_bound_windows_closed()) {
		fallback_timer_running_ = false;
		return;
	}
	const auto now = std::chrono::steady_clock::now();
	if (!fallback_timer_running_) {
		fallback_timer_running_ = true;
		fallback_timer_started_ = now;
		swap_debug("FALLBACK_PENDING all synchronized Dofus windows are closed");
		return;
	}
	if (!full_cam_active_ && now - fallback_timer_started_ >= config_.fallback_delay) {
		if (switch_to_scene(config_.fallback_scene)) {
			full_cam_active_ = true;
			swap_debug("FALLBACK_ACTIVE scene=" + config_.fallback_scene);
		}
	}
}

bool SceneGuard::setup_scenes(const GuardConfig &config, const std::vector<std::string> &parent_scenes)
{
	apply_config(config);
	// One-time migration for every built-in engine, regardless of the engine
	// currently selected in DOSOFT. Source references keep their transforms.
	migrate_scene_name("Jeu_Dofus_Unity", {"Jeu_Dofus", "DOSOFT — Dofus"});
	migrate_scene_name("Jeu_Dofus_Rétro", {"Jeu Dofus Retro"});
	migrate_scene_name("Jeu_Wakfu", {"Jeu Dofus Wakfu"});
	obs_scene_t *created_scene = nullptr;
	obs_source_t *game_source = find_scene(config_.game_scene);
	if (!game_source) {
		std::vector<std::string> legacy_names;
		if (config_.engine == "retro" || config_.engine == "rétro")
			legacy_names = {"Jeu Dofus Retro"};
		else if (config_.engine == "wakfu")
			legacy_names = {"Jeu Dofus Wakfu"};
		else
			legacy_names = {"Jeu_Dofus", "DOSOFT — Dofus"};
		for (const auto &legacy_name : legacy_names) {
			game_source = find_scene(legacy_name);
			if (!game_source)
				continue;
			obs_source_set_name(game_source, config_.game_scene.c_str());
			swap_debug("SETUP_RENAME scene=" + legacy_name + " -> " + config_.game_scene);
			break;
		}
	}
	if (!game_source) {
		created_scene = obs_scene_create(config_.game_scene.c_str());
		if (!created_scene) {
			swap_debug("SETUP_ERROR unable to create game scene=" + config_.game_scene);
			return false;
		}
		game_source = obs_source_get_ref(obs_scene_get_source(created_scene));
		swap_debug("SETUP_CREATE scene=" + config_.game_scene);
	}
	bool ok = true;
	for (const auto &parent_name : parent_scenes) {
		if (parent_name.empty() || parent_name == config_.game_scene)
			continue;
		obs_source_t *parent_source = find_scene(parent_name);
		if (!parent_source) {
			ok = false;
			swap_debug("SETUP_ERROR parent scene missing=" + parent_name);
			continue;
		}
		obs_scene_t *parent = obs_scene_from_source(parent_source);
		if (!obs_scene_find_source(parent, config_.game_scene.c_str())) {
			obs_sceneitem_t *item = obs_scene_add(parent, game_source);
			if (!item)
				ok = false;
			else
				swap_debug("SETUP_LINK game_scene=" + config_.game_scene + " parent=" + parent_name);
		}
		obs_source_release(parent_source);
	}
	obs_source_release(game_source);
	if (created_scene)
		obs_scene_release(created_scene);
	if (ok)
		obs_frontend_save();
	return ok;
}

bool SceneGuard::cleanup_scene_duplicates(const std::string &canonical_name)
{
	obs_source_t *canonical_source = find_scene(canonical_name);
	if (!canonical_source) {
		swap_debug("CLEANUP_ERROR canonical scene missing=" + canonical_name);
		return false;
	}
	obs_scene_t *canonical = obs_scene_from_source(canonical_source);
	SweepDuplicateReferenceContext stale_references{canonical_source, canonical_name, 0, false};
	obs_enum_scenes(sweep_duplicate_references, &stale_references);
	DuplicateSceneContext duplicates{canonical_name, {}};
	obs_enum_scenes(collect_generated_scene_duplicate, &duplicates);

	size_t merged = 0;
	for (obs_source_t *duplicate_source : duplicates.sources) {
		obs_scene_t *duplicate = obs_scene_from_source(duplicate_source);
		MergeSceneContext merge{canonical, 0};
		if (duplicate)
			obs_scene_enum_items(duplicate, merge_scene_item, &merge);
		merged += merge.merged;

		ReplaceSceneReferenceContext references{duplicate_source, canonical_source, 0};
		obs_enum_scenes(replace_scene_references, &references);
		const std::string duplicate_name = obs_source_get_name(duplicate_source);
		obs_source_remove(duplicate_source);
		obs_source_release(duplicate_source);
		swap_debug("CLEANUP_REMOVE duplicate scene=" + duplicate_name +
			   " references=" + std::to_string(references.replaced));
	}
	obs_source_release(canonical_source);
	obs_frontend_save();
	swap_debug("CLEANUP_DONE canonical=" + canonical_name +
		   " duplicates=" + std::to_string(duplicates.sources.size()) +
		   " merged_items=" + std::to_string(merged) +
		   " stale_references=" + std::to_string(stale_references.removed));
	return true;
}

void SceneGuard::shutdown()
{
	while (!prewarmed_captures_.empty())
		release_prewarm(prewarmed_captures_.begin()->first);
}

SceneGuard &scene_guard()
{
	static SceneGuard guard;
	return guard;
}

}  // namespace dofus_scene_guard
