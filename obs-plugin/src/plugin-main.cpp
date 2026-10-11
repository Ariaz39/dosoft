#include "adapters/dosoft_pipe_server.hpp"
#include "core/scene_guard.hpp"

#include <obs-module.h>
#include <obs-frontend-api.h>

#include <atomic>

OBS_DECLARE_MODULE()

MODULE_EXPORT const char *obs_module_description(void)
{
	return "Optional DOSOFT extension for guided OBS setup and protected Dofus capture switching.";
}

namespace {
std::atomic_bool pipe_started = false;

void frontend_event(enum obs_frontend_event event, void *)
{
	if (event == OBS_FRONTEND_EVENT_FINISHED_LOADING && !pipe_started.exchange(true)) {
		dofus_scene_guard::start_dosoft_pipe_server();
		blog(LOG_INFO, "[Dofus Scene Guard] OBS frontend ready; listening for DOSOFT on \\\\.\\pipe\\DofusSceneGuard");
	}
}

void foreground_tick(void *, float seconds)
{
	static float elapsed = 0.0F;
	elapsed += seconds;
	if (elapsed < 0.10F)
		return;
	elapsed = 0.0F;
	obs_queue_task(
		OBS_TASK_UI,
		[](void *) { dofus_scene_guard::scene_guard().poll_foreground_window(); },
		nullptr, false);
}
}

bool obs_module_load(void)
{
	obs_frontend_add_event_callback(frontend_event, nullptr);
	obs_add_tick_callback(foreground_tick, nullptr);
	blog(LOG_INFO, "[Dofus Scene Guard] loaded; waiting for OBS frontend readiness");
	return true;
}

void obs_module_unload(void)
{
	obs_remove_tick_callback(foreground_tick, nullptr);
	obs_frontend_remove_event_callback(frontend_event, nullptr);
	dofus_scene_guard::stop_dosoft_pipe_server();
	dofus_scene_guard::scene_guard().shutdown();
}
