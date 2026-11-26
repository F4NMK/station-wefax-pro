import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Window
import "components" as C
import "panels"

/*
 * main.qml — Fenêtre racine de Station WEFAX PRO (interface Qt)
 *
 * Context properties enregistrées par launcher_qt.py :
 *   radio : RadioBridge
 *   dsp   : DspBridge
 *   app   : AppBridge
 */
ApplicationWindow {
    id:       mainWindow
    title:    "Station WEFAX PRO — Qt Edition"
    width:    1280
    height:   820
    minimumWidth:  900
    minimumHeight: 600
    visible:  true
    color:    "#131922"   // Theme.bgRoot — littéral ici, singleton chargé ci-dessous

    // ── Singleton thème ─────────────────────────────────────────────────
    // (déclaré dans qmldir, importé implicitement sous ".")
    // On y accède via T.Theme depuis les fichiers enfants.

    // ── État global ─────────────────────────────────────────────────────
    property int    currentTab:   0
    property string appStatus:    "Démarrage…"
    property bool   audioOk:      false
    property string currentMode:  "IDLE"

    Connections {
        target: app
        function onStatusChanged(text)   { mainWindow.appStatus = text }
        function onModeChanged(mode)     { mainWindow.currentMode = mode }
        function onAudioConnected(ok)    { mainWindow.audioOk = ok }
        function onVersionReady(ver)     { mainWindow.title = "Station WEFAX PRO " + ver + " — Qt Edition" }
    }

    // ── Layout principal ─────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Barre d'onglets ─────────────────────────────────────────────
        C.TabBar {
            id: mainTabBar
            Layout.fillWidth: true
            model: ["RADIO", "IMAGE", "MÉTÉO", "PLAN"]
            currentIndex: mainWindow.currentTab
            onTabSelected: mainWindow.currentTab = index

            // Propriétés thème transmises explicitement
            bgColor:      "#1b2430"
            borderColor:  "#2e3d4f"
            accentColor:  "#2563eb"
            textActive:   "#e6edf3"
            textInactive: "#64748b"
        }

        // ── Zone de contenu (StackLayout) ───────────────────────────────
        StackLayout {
            id: contentStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: mainWindow.currentTab

            RadioPanel { id: radioPanel }
            ImagePanel { id: imagePanel }
            MeteoPanel { id: meteoPanel }
            PlanPanel  { id: planPanel  }
        }

        // ── Barre de statut ─────────────────────────────────────────────
        C.StatusBar {
            Layout.fillWidth: true
            statusText:     mainWindow.appStatus
            modeText:       mainWindow.currentMode
            mode:           mainWindow.currentMode
            audioConnected: mainWindow.audioOk
        }
    }

    // ── Fermeture propre ─────────────────────────────────────────────────
    onClosing: function(close) {
        close.accepted = false   // on laisse AppBridge décider
        app.requestClose()
    }

    Connections {
        target: app
        function onClosingApp() { Qt.quit() }
    }

    // ── Initialisation ───────────────────────────────────────────────────
    Component.onCompleted: {
        app.initialize()
    }
}
