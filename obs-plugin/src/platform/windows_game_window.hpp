#pragma once

#include "../core/scene_resolver.hpp"

#include <optional>
#include <string>

namespace dofus_scene_guard {

std::optional<ActiveGameInstance> foreground_dofus_window(const std::string &engine);
bool has_valid_dofus_window(const std::vector<SceneBinding> &instances);
bool has_any_dofus_window(const std::vector<SceneBinding> &instances);
std::string game_capture_window_id(std::uintptr_t hwnd);

}  // namespace dofus_scene_guard
