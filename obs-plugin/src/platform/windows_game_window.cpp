#include "windows_game_window.hpp"

#include <windows.h>

#include <iterator>
#include <algorithm>
#include <cctype>
#include <cwctype>
#include <string>

namespace dofus_scene_guard {
namespace {
std::string utf8(const std::wstring &value)
{
	if (value.empty())
		return {};
	const int size = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, nullptr, 0, nullptr, nullptr);
	std::string result(size, '\0');
	WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, result.data(), size, nullptr, nullptr);
	result.pop_back();
	return result;
}

std::wstring window_text(HWND hwnd)
{
	const int length = GetWindowTextLengthW(hwnd);
	std::wstring text(length + 1, L'\0');
	GetWindowTextW(hwnd, text.data(), length + 1);
	text.resize(length);
	return text;
}

std::wstring window_class(HWND hwnd)
{
	wchar_t value[256]{};
	GetClassNameW(hwnd, value, static_cast<int>(std::size(value)));
	return value;
}

std::wstring executable_name(HWND hwnd)
{
	DWORD pid{};
	GetWindowThreadProcessId(hwnd, &pid);
	HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
	if (!process)
		return {};
	wchar_t path[MAX_PATH]{};
	DWORD size = MAX_PATH;
	const bool found = QueryFullProcessImageNameW(process, 0, path, &size);
	CloseHandle(process);
	if (!found)
		return {};
	const std::wstring full_path(path, size);
	return full_path.substr(full_path.find_last_of(L"\\/") + 1);
}

std::wstring lowercase(std::wstring value)
{
	std::transform(value.begin(), value.end(), value.begin(),
		       [](wchar_t character) { return static_cast<wchar_t>(std::towlower(character)); });
	return value;
}

std::string normalized_engine(std::string engine)
{
	std::transform(engine.begin(), engine.end(), engine.begin(),
		       [](unsigned char character) { return static_cast<char>(std::tolower(character)); });
	if (engine == "rétro" || engine == "retro")
		return "retro";
	if (engine == "wakfu")
		return "wakfu";
	return "unity";
}

bool matches_engine(HWND hwnd, const std::string &engine)
{
	if (!hwnd || !IsWindow(hwnd))
		return false;
	const std::wstring klass = window_class(hwnd);
	const std::wstring title = lowercase(window_text(hwnd));
	const std::wstring executable = lowercase(executable_name(hwnd));
	if (title.empty())
		return false;
	const std::string normalized = normalized_engine(engine);
	if (normalized == "retro")
		return klass == L"Chrome_WidgetWin_1" && executable == L"dofus retro.exe" &&
		       title.find(L"dofus retro") != std::wstring::npos;
	if (normalized == "wakfu")
		return klass == L"SunAwtFrame" && executable == L"javaw.exe" &&
		       title.find(L"wakfu") != std::wstring::npos;
	return klass == L"UnityWndClass";
}

bool is_dofus_window(HWND hwnd, const std::string &engine)
{
	if (!IsWindowVisible(hwnd) || IsIconic(hwnd))
		return false;
	return matches_engine(hwnd, engine);
}

// Unlike the foreground test, a minimized Dofus client remains a healthy
// stream source.  This is used solely to detect a real close/crash.
bool is_existing_dofus_window(HWND hwnd, const std::string &engine)
{
	return matches_engine(hwnd, engine);
}
}

std::optional<ActiveGameInstance> foreground_dofus_window(const std::string &engine)
{
	HWND hwnd = GetForegroundWindow();
	if (!is_dofus_window(hwnd, engine))
		return std::nullopt;
	return ActiveGameInstance{"", utf8(window_text(hwnd)), reinterpret_cast<std::uintptr_t>(hwnd),
				  normalized_engine(engine)};
}

bool has_valid_dofus_window(const std::vector<SceneBinding> &instances)
{
	for (const auto &instance : instances) {
		if (is_existing_dofus_window(reinterpret_cast<HWND>(instance.hwnd), instance.engine))
			return true;
	}
	return false;
}

bool has_any_dofus_window(const std::vector<SceneBinding> &instances)
{
	return has_valid_dofus_window(instances);
}

std::string game_capture_window_id(std::uintptr_t handle)
{
	const HWND hwnd = reinterpret_cast<HWND>(handle);
	return utf8(window_text(hwnd)) + ":" + utf8(window_class(hwnd)) + ":" + utf8(executable_name(hwnd));
}

}  // namespace dofus_scene_guard
