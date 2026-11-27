import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Window
import "components" as C
import "panels"
import "." as T

/*
 * main.qml — Fenêtre racine de Station WEFAX PRO (interface Qt)
 *
 * Context properties enregistrées par launcher_qt.py :
 *   radio     : RadioBridge
 *   dsp       : DspBridge
 *   appBridge : AppBridge
 *
 * Onglets :
 *   0  RADIO   — contrôle IC-705, scan, RF
 *   1  IMAGE   — WEFAX décodage + DSP
 *   2  RTTY    — téléimprimeur RTTY / NAVTEX
 *   3  MÉTÉO   — synoptique + bulletins + analyse physique
 *   4  PLAN    — programme émissions UTC
 *   5  WINLINK — session Winlink/VARA, envoi images, GRIB
 *   6  ARCHIVES — historique cartes reçues, export signé
 *   7  CONFIG  — paramètres + switch UI
 */
ApplicationWindow {
    id:            mainWindow
    title:         "Station WEFAX PRO — Qt Edition"
    width:         1280
    height:        820
    minimumWidth:  900
    minimumHeight: 600
    visible:       true
    color:         T.Theme.bgRoot

    // ── État global ──────────────────────────────────────────────────────────
    property int    currentTab:   0
    property string appStatus:    "Démarrage…"
    property bool   audioOk:      false
    property string currentMode:  "IDLE"

    // ── Connexions AppBridge ─────────────────────────────────────────────────
    Connections {
        target: appBridge
        function onStatusChanged(text)   { mainWindow.appStatus = text }
        function onModeChanged(mode)     { mainWindow.currentMode = mode }
        function onAudioConnected(ok)    { mainWindow.audioOk = ok }
        function onVersionReady(ver)     { mainWindow.title = "Station WEFAX PRO " + ver + " — Qt Edition" }
        function onClosingApp()          { Qt.quit() }
    }

    // ── Layout principal ─────────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Barre d'onglets ───────────────────────────────────────────────
        C.TabBar {
            id: mainTabBar
            Layout.fillWidth: true
            model: ["📡 RADIO", "🖼 IMAGE", "🔤 RTTY", "🌦 MÉTÉO", "📅 PLAN", "🌐 WINLINK", "🗂 ARCHIVES", "⚙ CONFIG"]
            currentIndex: mainWindow.currentTab
            onTabSelected: (idx) => mainWindow.currentTab = idx

            bgColor:      T.Theme.bgPanel
            borderColor:  T.Theme.border
            accentColor:  T.Theme.accent
            textActive:   T.Theme.textPrimary
            textInactive: T.Theme.textDim
        }

        // ── Contenu ───────────────────────────────────────────────────────
        StackLayout {
            id: contentStack
            Layout.fillWidth:  true
            Layout.fillHeight: true
            clip: true
            currentIndex: mainWindow.currentTab

            RadioPanel    { id: radioPanel    }
            ImagePanel    { id: imagePanel    }
            RttyPanel     { id: rttyPanel     }
            MeteoPanel    { id: meteoPanel    }
            PlanPanel     { id: planPanel     }
            WinlinkPanel  { id: winlinkPanel  }
            ArchivesPanel { id: archivesPanel }
            SettingsPanel { id: settingsPanel }
        }

        // ── Barre de statut ───────────────────────────────────────────────
        C.StatusBar {
            Layout.fillWidth: true
            statusText:     mainWindow.appStatus
            modeText:       mainWindow.currentMode
            mode:           mainWindow.currentMode
            audioConnected: mainWindow.audioOk
        }
    }

    // ── Fermeture propre ─────────────────────────────────────────────────────
    onClosing: function(close) {
        close.accepted = false
        appBridge.requestClose()
    }

    // ── Raccourcis clavier ───────────────────────────────────────────────────
    Shortcut {
        sequence: "Ctrl+1"; onActivated: mainWindow.currentTab = 0
    }
    Shortcut {
        sequence: "Ctrl+2"; onActivated: mainWindow.currentTab = 1
    }
    Shortcut {
        sequence: "Ctrl+3"; onActivated: mainWindow.currentTab = 2
    }
    Shortcut {
        sequence: "Ctrl+4"; onActivated: mainWindow.currentTab = 3
    }
    Shortcut {
        sequence: "Ctrl+5"; onActivated: mainWindow.currentTab = 4
    }
    Shortcut {
        sequence: "Ctrl+6"; onActivated: mainWindow.currentTab = 5
    }
    Shortcut {
        sequence: "Ctrl+7"; onActivated: mainWindow.currentTab = 6
    }
    Shortcut {
        sequence: "Ctrl+8"; onActivated: mainWindow.currentTab = 7
    }
    Shortcut {
        sequence: "Ctrl+Q"
        onActivated: appBridge.requestClose()
    }

    // ── Initialisation ───────────────────────────────────────────────────────
    Component.onCompleted: {
        appBridge.initialize()
    }
}
