#pragma once

namespace dofus_scene_guard {

// Receives validated local DOSOFT events. Named-pipe implementation to come.
class DosoftBridge {
 public:
  void start();
  void stop();
};

}  // namespace dofus_scene_guard
