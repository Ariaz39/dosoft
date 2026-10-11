cmake_minimum_required(VERSION 3.28...3.30)
project(dofus-scene-guard VERSION 0.3.1 LANGUAGES CXX)

# The regular OBS installer does not ship this SDK. Point OBS_SDK_DIR at an
# OBS 32 development SDK containing include/ and lib/ directories.
set(OBS_SDK_DIR "" CACHE PATH "Path to the OBS Studio development SDK")
find_path(OBS_INCLUDE_DIR obs-module.h HINTS "${OBS_SDK_DIR}/include" "${OBS_SDK_DIR}/libobs")
find_path(OBS_FRONTEND_INCLUDE_DIR obs-frontend-api.h HINTS "${OBS_SDK_DIR}/include" "${OBS_SDK_DIR}/frontend/api")
find_library(OBS_LIBRARY NAMES obs PATHS "${OBS_SDK_DIR}/lib")
find_library(OBS_FRONTEND_LIBRARY NAMES obs-frontend-api PATHS "${OBS_SDK_DIR}/lib")
if(NOT OBS_INCLUDE_DIR OR NOT OBS_FRONTEND_INCLUDE_DIR OR NOT OBS_LIBRARY OR NOT OBS_FRONTEND_LIBRARY)
  message(FATAL_ERROR "OBS 32 development SDK not found. Set OBS_SDK_DIR to the SDK root.")
endif()

# obs-config.h includes a generated configuration header. Only the public API
# headers are required for this plugin, so generate the neutral SDK variant.
set(OBS_DATA_PATH "data")
set(OBS_PLUGIN_PATH "obs-plugins")
set(OBS_PLUGIN_DESTINATION "obs-plugins/64bit")
set(OBS_RELEASE_CANDIDATE 0)
set(OBS_BETA 0)
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/config")
configure_file("${OBS_SDK_DIR}/libobs/obsconfig.h.in"
               "${CMAKE_BINARY_DIR}/config/obsconfig.h" @ONLY)

add_library(dofus-scene-guard MODULE
  src/plugin-main.cpp
  src/core/scene_guard.cpp
  src/platform/windows_game_window.cpp
  src/adapters/dosoft_pipe_server.cpp
)

target_compile_features(dofus-scene-guard PRIVATE cxx_std_20)
target_include_directories(dofus-scene-guard PRIVATE "${OBS_INCLUDE_DIR}" "${OBS_FRONTEND_INCLUDE_DIR}" "${CMAKE_BINARY_DIR}/config")
target_link_libraries(dofus-scene-guard PRIVATE "${OBS_LIBRARY}" "${OBS_FRONTEND_LIBRARY}")
target_compile_definitions(dofus-scene-guard PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN)
set_target_properties(dofus-scene-guard PROPERTIES PREFIX "")

install(TARGETS dofus-scene-guard LIBRARY DESTINATION "obs-plugins/64bit")
