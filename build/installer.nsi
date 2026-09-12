; ─────────────────────────────────────────────────────────────────────────────
; Battery Lens — Windows NSIS Installer
; Requires: NSIS 3.x (https://nsis.sourceforge.io)
;
; Build command (from project root):
;   makensis /DAPP_VERSION=1.0.0 build\installer.nsi
;
; Output: build\output\BatteryLens-Setup.exe
; ─────────────────────────────────────────────────────────────────────────────

Unicode True

; ── Defaults (overridden via /D on command line) ─────────────────────────────
!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif

!define APP_NAME        "Battery Lens"
!define APP_EXE         "BatteryLens.exe"
!define APP_PUBLISHER   "Battery Lens"
!define APP_URL         "https://github.com/your-username/battery-lens"
!define BUNDLE_ID       "BatteryLens"
!define DIST_DIR        "..\dist\BatteryLens"
!define ASSETS_DIR      "..\assets"

; No admin required — installs to user's local AppData
RequestExecutionLevel user
SetCompressor /SOLID lzma

; Output file
OutFile "..\dist\BatteryLens-Setup.exe"

; Default install to user's LocalAppData (no admin, no UAC prompt)
InstallDir "$LOCALAPPDATA\${BUNDLE_ID}"
InstallDirRegKey HKCU "Software\${BUNDLE_ID}" "InstallPath"

; ── Modern UI ─────────────────────────────────────────────────────────────────
!include "MUI2.nsh"
!include "WinVer.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "${ASSETS_DIR}\icon.ico"
!define MUI_UNICON "${ASSETS_DIR}\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP_NOSTRETCH
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP_NOSTRETCH

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; Finish page — offer to launch app immediately
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Battery Lens now"
!define MUI_FINISHPAGE_SHOWREADME ""
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Version info embedded in the EXE ──────────────────────────────────────────
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "CompanyName"     "${APP_PUBLISHER}"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "ProductVersion"  "${APP_VERSION}"
VIAddVersionKey "FileDescription" "Battery Lens Installer"
VIAddVersionKey "LegalCopyright"  "© 2026 ${APP_PUBLISHER}"

; ── Install Section ────────────────────────────────────────────────────────────
Section "Battery Lens" SecMain
  SectionIn RO  ; Required section, cannot be deselected

  SetOutPath "$INSTDIR"

  ; Copy all PyInstaller output files
  File /r "${DIST_DIR}\*.*"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0 \
    SW_SHOWNORMAL "" "Battery monitoring in the system tray"

  ; Start Menu entries
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0 \
    SW_SHOWNORMAL "" "Battery monitoring in the system tray"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
    "$INSTDIR\Uninstall.exe"

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Add/Remove Programs entry (HKCU — no admin needed)
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "DisplayName"     "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "URLInfoAbout"    "${APP_URL}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}" \
    "NoRepair" 1

  ; Save install path for future reference
  WriteRegStr HKCU "Software\${BUNDLE_ID}" "InstallPath" "$INSTDIR"
  WriteRegStr HKCU "Software\${BUNDLE_ID}" "Version"     "${APP_VERSION}"
SectionEnd

; ── Uninstall Section ──────────────────────────────────────────────────────────
Section "Uninstall"
  ; Stop the app if running
  ExecWait 'taskkill /F /IM "${APP_EXE}"' $0

  ; Remove installed files
  RMDir /r "$INSTDIR"

  ; Remove shortcuts
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"

  ; Remove registry entries
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${BUNDLE_ID}"
  DeleteRegKey HKCU "Software\${BUNDLE_ID}"

  ; Remove from Windows startup if user had enabled it
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${BUNDLE_ID}"
SectionEnd
