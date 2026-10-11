#pragma once

#include "scene_resolver.hpp"

#include <string>
#include <unordered_map>
#include <vector>
#include <chrono>

struct obs_source;
struct obs_weak_source;
struct obs_scene_item;

namespace dofus_scene_guard {

struct GuardConfig {
  std::string stream_scene = "Stream";
  std::string game_scene = "DOSOFT — Dofus";
  std::string fallback_scene;
  std::string capture_prefix = "DOSOFT Dofus — ";
  std::string engine = "unity";
  size_t maximum_captures = 12;
  bool fallback_enabled = false;
  std::chrono::milliseconds fallback_delay{2000};
};

struct ControlResult {
  bool ok = false;
  bool stateful = false;
  bool off = false;
};

class SceneGuard {
 public:
  bool synchronize_team(const std::vector<ActiveGameInstance> &accounts,
                        const GuardConfig &config, std::uint64_t revision);
  bool rebuild_team(const std::vector<ActiveGameInstance> &accounts,
                    const GuardConfig &config, std::uint64_t revision);
  void set_auto_swap(bool enabled);
  ControlResult control(const std::string &command, const std::string &source,
                        const std::string &scene);
  ControlResult control_state(const std::string &command, const std::string &source,
                              const std::string &scene);
  bool select_account(const ActiveGameInstance &account);
  bool setup_scenes(const GuardConfig &config, const std::vector<std::string> &parent_scenes);
  bool cleanup_scene_duplicates(const std::string &canonical_name);
  void poll_foreground_window();
  void shutdown();

 private:
  bool switch_to_scene(const std::string &scene_name);
  bool ensure_capture_in_game_scene(const ActiveGameInstance &account);
  bool show_only_capture(const SceneBinding &binding, const ActiveGameInstance &account);
  bool update_capture_target(::obs_scene_item *item, const ActiveGameInstance &account);
  size_t managed_capture_count();
  void clear_game_captures(const char *reason);
  void release_prewarm(const std::string &capture_name);
  void prewarm_capture(::obs_source *capture, const std::string &capture_name);
  void restore_after_recovery();
  void apply_config(const GuardConfig &config);
  std::string capture_name_for(const ActiveGameInstance &account) const;
  bool all_bound_windows_closed() const;

  SceneResolver resolver_;
  GuardConfig config_;
  bool auto_swap_enabled_ = false;
  bool team_synchronized_ = false;
  bool full_cam_active_ = false;
  bool fallback_timer_running_ = false;
  std::chrono::steady_clock::time_point fallback_timer_started_{};
  std::uintptr_t last_foreground_hwnd_ = 0;
  std::string last_selected_client_id_;
  std::uint64_t latest_revision_ = 0;
  std::unordered_map<std::string, ::obs_weak_source *> prewarmed_captures_;
};

SceneGuard &scene_guard();

}  // namespace dofus_scene_guard
