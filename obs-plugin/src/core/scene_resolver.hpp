#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace dofus_scene_guard {

struct ActiveGameInstance {
  std::string client_id;
  std::string account;
  std::uintptr_t hwnd{};
  std::string engine = "unity";
};

struct SceneBinding {
  std::string client_id;
  std::string account;
  std::uintptr_t hwnd{};
  std::string capture_name;
  std::string engine = "unity";
};

// Resolves only configured Dofus instances. An unmatched foreground window
// deliberately yields no scene change, protecting the live output.
class SceneResolver {
 public:
  void replace_bindings(std::vector<SceneBinding> bindings);
  std::optional<SceneBinding> resolve(const ActiveGameInstance &instance) const;
  const std::vector<SceneBinding> &bindings() const { return bindings_; }

 private:
  std::vector<SceneBinding> bindings_;
};

}  // namespace dofus_scene_guard
