#include "dosoft_pipe_server.hpp"

#include "../core/scene_guard.hpp"

#include <obs-frontend-api.h>
#include <obs-module.h>

#include <windows.h>

#include <atomic>
#include <chrono>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace dofus_scene_guard {
namespace {
constexpr wchar_t kPipeName[] = L"\\\\.\\pipe\\DofusSceneGuard";
constexpr int kProtocolVersion = 3;
constexpr int kMinimumProtocolVersion = 2;
constexpr char kPluginVersion[] = "0.3.1";
std::atomic_bool running = false;
std::thread server_thread;
const std::string session_id = std::to_string(GetCurrentProcessId()) + "-" +
			       std::to_string(GetTickCount64());

enum class ActionType {
	Hello, Sync, Rebuild, Select, AutoSwap, Control, ControlState, Inventory, Setup,
	CleanupDuplicates, Deactivate
};
struct PipeAction {
	ActionType type;
	int protocol_version = kProtocolVersion;
	std::vector<ActiveGameInstance> accounts;
	ActiveGameInstance account;
	GuardConfig config;
	std::vector<std::string> parent_scenes;
	bool enabled = false;
	std::uint64_t revision = 0;
	std::string command, source, scene;
	bool ok = false;
	std::string response_data;
};

std::string string_field(obs_data_t *data, const char *name)
{
	const char *value = obs_data_get_string(data, name);
	return value ? value : "";
}

std::string json_escape(const std::string &value)
{
	std::ostringstream out;
	for (unsigned char character : value) {
		switch (character) {
		case '"': out << "\\\""; break;
		case '\\': out << "\\\\"; break;
		case '\b': out << "\\b"; break;
		case '\f': out << "\\f"; break;
		case '\n': out << "\\n"; break;
		case '\r': out << "\\r"; break;
		case '\t': out << "\\t"; break;
		default:
			if (character < 0x20)
				out << "?";
			else
				out << character;
		}
	}
	return out.str();
}

std::string json_array(const std::vector<std::string> &values)
{
	std::ostringstream out;
	out << '[';
	for (size_t index = 0; index < values.size(); ++index) {
		if (index)
			out << ',';
		out << '"' << json_escape(values[index]) << '"';
	}
	out << ']';
	return out.str();
}

GuardConfig parse_config(obs_data_t *root)
{
	GuardConfig config;
	obs_data_t *profile = obs_data_get_obj(root, "profile");
	if (!profile)
		profile = root;
	const std::string stream_scene = string_field(profile, "stream_scene");
	const std::string game_scene = string_field(profile, "game_scene");
	const std::string fallback_scene = string_field(profile, "fallback_scene");
	const std::string capture_prefix = string_field(profile, "capture_prefix");
	const std::string engine = string_field(profile, "engine");
	if (!stream_scene.empty()) config.stream_scene = stream_scene;
	if (!game_scene.empty()) config.game_scene = game_scene;
	if (!fallback_scene.empty()) config.fallback_scene = fallback_scene;
	if (!capture_prefix.empty()) config.capture_prefix = capture_prefix;
	if (!engine.empty()) config.engine = engine;
	const long long maximum = obs_data_get_int(profile, "max_captures");
	if (maximum > 0) config.maximum_captures = static_cast<size_t>(maximum);
	config.fallback_enabled = obs_data_get_bool(profile, "fallback_enabled");
	const long long delay = obs_data_get_int(profile, "fallback_delay_ms");
	if (delay > 0) config.fallback_delay = std::chrono::milliseconds(delay);
	if (profile != root)
		obs_data_release(profile);
	return config;
}

std::vector<std::string> string_array(obs_data_t *root, const char *field)
{
	std::vector<std::string> values;
	obs_data_array_t *array = obs_data_get_array(root, field);
	if (!array)
		return values;
	const size_t count = obs_data_array_count(array);
	for (size_t index = 0; index < count; ++index) {
		obs_data_t *entry = obs_data_array_item(array, index);
		const std::string value = string_field(entry, "value");
		if (!value.empty())
			values.push_back(value);
		obs_data_release(entry);
	}
	obs_data_array_release(array);
	return values;
}

struct Inventory {
	std::vector<std::string> scenes;
	std::vector<std::string> sources;
	std::vector<std::string> audio_sources;
	std::string current_scene;
};

bool collect_source(void *opaque, obs_source_t *source)
{
	auto *inventory = static_cast<Inventory *>(opaque);
	const char *name = obs_source_get_name(source);
	if (!name || !*name)
		return true;
	if (obs_scene_from_source(source))
		inventory->scenes.emplace_back(name);
	else
		inventory->sources.emplace_back(name);
	if (obs_source_get_output_flags(source) & OBS_SOURCE_AUDIO)
		inventory->audio_sources.emplace_back(name);
	return true;
}

std::string inventory_json()
{
	Inventory inventory;
	obs_enum_all_sources(collect_source, &inventory);
	obs_source_t *current = obs_frontend_get_current_scene();
	if (current) {
		inventory.current_scene = obs_source_get_name(current);
		obs_source_release(current);
	}
	return "{\"plugin_version\":\"" + std::string(kPluginVersion) +
	       "\",\"obs_version\":\"" + json_escape(obs_get_version_string()) +
	       "\",\"protocol_version\":" + std::to_string(kProtocolVersion) +
	       ",\"protocol_min\":" + std::to_string(kMinimumProtocolVersion) +
	       ",\"session_id\":\"" + json_escape(session_id) +
	       "\",\"capabilities\":[\"inventory\",\"setup_scenes\",\"sync_team\","
	       "\"rebuild_team\",\"account_selection\",\"auto_swap\",\"obs_control\",\"obs_control_state\","
	       "\"multi_engine\",\"cursor_capture\",\"fallback_scene\"],\"current_scene\":\"" +
	       json_escape(inventory.current_scene) + "\",\"scenes\":" + json_array(inventory.scenes) +
	       ",\"sources\":" + json_array(inventory.sources) +
	       ",\"audio_sources\":" + json_array(inventory.audio_sources) + "}";
}

std::string handshake_json()
{
	return "{\"plugin_version\":\"" + std::string(kPluginVersion) +
	       "\",\"obs_version\":\"" + json_escape(obs_get_version_string()) +
	       "\",\"protocol_version\":" + std::to_string(kProtocolVersion) +
	       ",\"protocol_min\":" + std::to_string(kMinimumProtocolVersion) +
	       ",\"session_id\":\"" + json_escape(session_id) +
	       "\",\"capabilities\":[\"inventory\",\"setup_scenes\",\"sync_team\","
	       "\"rebuild_team\",\"account_selection\",\"auto_swap\",\"obs_control\",\"obs_control_state\","
	       "\"multi_engine\",\"cursor_capture\",\"fallback_scene\"]}";
}

void apply_action(void *opaque)
{
	auto *action = static_cast<PipeAction *>(opaque);
	switch (action->type) {
	case ActionType::Hello:
		action->response_data = handshake_json();
		action->ok = true;
		break;
	case ActionType::Sync:
		action->ok = scene_guard().synchronize_team(action->accounts, action->config, action->revision);
		scene_guard().set_auto_swap(action->enabled);
		break;
	case ActionType::Rebuild:
		action->ok = scene_guard().rebuild_team(action->accounts, action->config, action->revision);
		scene_guard().set_auto_swap(action->enabled);
		break;
	case ActionType::Select:
		action->ok = scene_guard().select_account(action->account);
		break;
	case ActionType::AutoSwap:
		scene_guard().set_auto_swap(action->enabled);
		action->ok = true;
		break;
	case ActionType::Control:
	{
		const ControlResult result = scene_guard().control(
			action->command, action->source, action->scene);
		action->ok = result.ok;
		action->response_data = std::string("{\"stateful\":") +
			(result.stateful ? "true" : "false") + ",\"off\":" +
			(result.off ? "true" : "false") + "}";
		break;
	}
	case ActionType::ControlState:
	{
		const ControlResult result = scene_guard().control_state(
			action->command, action->source, action->scene);
		action->ok = result.ok;
		action->response_data = std::string("{\"stateful\":") +
			(result.stateful ? "true" : "false") + ",\"off\":" +
			(result.off ? "true" : "false") + "}";
		break;
	}
	case ActionType::Inventory:
		action->response_data = inventory_json();
		action->ok = true;
		break;
	case ActionType::Setup:
		action->ok = scene_guard().setup_scenes(action->config, action->parent_scenes);
		break;
	case ActionType::CleanupDuplicates:
		action->ok = scene_guard().cleanup_scene_duplicates(action->config.game_scene);
		break;
	case ActionType::Deactivate:
		scene_guard().set_auto_swap(false);
		action->ok = true;
		break;
	}
}

std::string execute(std::unique_ptr<PipeAction> action, const std::string &request_id)
{
	obs_queue_task(OBS_TASK_UI, apply_action, action.get(), true);
	std::string response = "{\"version\":" + std::to_string(action->protocol_version) +
			       ",\"request_id\":\"" + json_escape(request_id) +
			       "\",\"ok\":" + (action->ok ? "true" : "false");
	if (!action->response_data.empty())
		response += ",\"data\":" + action->response_data;
	if (!action->ok)
		response += ",\"error\":\"operation_not_ready\"";
	response += "}";
	return response;
}

std::string parse_message(const std::string &message)
{
	obs_data_t *root = obs_data_create_from_json(message.c_str());
	if (!root)
		return "{\"version\":3,\"ok\":false,\"error\":\"invalid_json\"}";
	const std::string request_id = string_field(root, "request_id");
	const std::string event = string_field(root, "event");
	const long long protocol_version = obs_data_get_int(root, "version");
	if (protocol_version < kMinimumProtocolVersion || protocol_version > kProtocolVersion) {
		obs_data_release(root);
		return "{\"version\":3,\"request_id\":\"" + json_escape(request_id) +
		       "\",\"ok\":false,\"error\":\"unsupported_protocol\","
		       "\"protocol_min\":2,\"protocol_max\":3}";
	}
	if (request_id.empty() || request_id.size() > 64 || event.empty() || event.size() > 64) {
		obs_data_release(root);
		return "{\"version\":3,\"request_id\":\"" + json_escape(request_id) +
		       "\",\"ok\":false,\"error\":\"invalid_envelope\"}";
	}
	std::unique_ptr<PipeAction> action;
	if (event == "hello") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::Hello;
	} else if (event == "get_inventory") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::Inventory;
	} else if (event == "setup_scenes") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::Setup;
		action->config = parse_config(root);
		action->parent_scenes = string_array(root, "parent_scenes");
	} else if (event == "cleanup_scene_duplicates") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::CleanupDuplicates;
		action->config = parse_config(root);
	} else if (event == "sync_team" || event == "rebuild_team") {
		action = std::make_unique<PipeAction>();
		action->type = event == "rebuild_team" ? ActionType::Rebuild : ActionType::Sync;
		action->config = parse_config(root);
		action->enabled = obs_data_get_bool(root, "auto_swap");
		action->revision = static_cast<std::uint64_t>(obs_data_get_int(root, "revision"));
		obs_data_array_t *accounts = obs_data_get_array(root, "accounts");
		if (accounts) {
			const size_t count = obs_data_array_count(accounts);
			for (size_t index = 0; index < count; ++index) {
				obs_data_t *entry = obs_data_array_item(accounts, index);
				const auto hwnd = static_cast<std::uintptr_t>(obs_data_get_int(entry, "hwnd"));
				const std::string account = string_field(entry, "account");
				const std::string client_id = string_field(entry, "client_id");
				std::string engine = string_field(entry, "engine");
				if (engine.empty()) engine = action->config.engine;
				if (!account.empty() && hwnd)
					action->accounts.push_back({client_id, account, hwnd, engine});
				obs_data_release(entry);
			}
			obs_data_array_release(accounts);
		}
	} else if (event == "dofus_account_selected") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::Select;
		action->account.client_id = string_field(root, "client_id");
		action->account.account = string_field(root, "account");
		action->account.hwnd = static_cast<std::uintptr_t>(obs_data_get_int(root, "hwnd"));
		action->account.engine = string_field(root, "engine");
	} else if (event == "set_auto_swap") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::AutoSwap;
		action->enabled = obs_data_get_bool(root, "enabled");
	} else if (event == "obs_control") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::Control;
		action->command = string_field(root, "command");
		action->source = string_field(root, "source");
		action->scene = string_field(root, "scene");
	} else if (event == "obs_control_state") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::ControlState;
		action->command = string_field(root, "command");
		action->source = string_field(root, "source");
		action->scene = string_field(root, "scene");
	} else if (event == "deactivate") {
		action = std::make_unique<PipeAction>();
		action->type = ActionType::Deactivate;
	} else {
		obs_data_release(root);
		return "{\"version\":" + std::to_string(protocol_version) +
		       ",\"request_id\":\"" + json_escape(request_id) +
		       "\",\"ok\":false,\"error\":\"unknown_event\"}";
	}
	action->protocol_version = static_cast<int>(protocol_version);
	obs_data_release(root);
	return execute(std::move(action), request_id);
}

void server_loop()
{
	while (running) {
		HANDLE pipe = CreateNamedPipeW(kPipeName, PIPE_ACCESS_DUPLEX,
			PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
			1, 64 * 1024, 64 * 1024, 0, nullptr);
		if (pipe == INVALID_HANDLE_VALUE)
			return;
		const BOOL connected = ConnectNamedPipe(pipe, nullptr) || GetLastError() == ERROR_PIPE_CONNECTED;
		if (connected) {
			char buffer[64 * 1024]{};
			DWORD read{};
			if (ReadFile(pipe, buffer, sizeof(buffer) - 1, &read, nullptr) && read) {
				const std::string response = parse_message(std::string(buffer, read));
				DWORD written{};
				WriteFile(pipe, response.data(), static_cast<DWORD>(response.size()), &written, nullptr);
				FlushFileBuffers(pipe);
			}
		}
		DisconnectNamedPipe(pipe);
		CloseHandle(pipe);
	}
}
}

void start_dosoft_pipe_server()
{
	if (!running.exchange(true))
		server_thread = std::thread(server_loop);
}

void stop_dosoft_pipe_server()
{
	if (!running.exchange(false))
		return;
	HANDLE pipe = CreateFileW(kPipeName, GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
	if (pipe != INVALID_HANDLE_VALUE)
		CloseHandle(pipe);
	if (server_thread.joinable())
		server_thread.join();
}

}  // namespace dofus_scene_guard
