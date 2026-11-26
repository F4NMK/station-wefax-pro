import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../components" as C
import ".." as T

/*
 * RadioPanel.qml — Onglet RADIO (complet)
 *
 * Context properties attendus :
 *   radio  : RadioBridge  (signaux freqChanged, modeChanged, handshakeChanged, smeterChanged, logMessage,
 *                           preampChanged, attChanged, filterChanged, scanProgress, scanCompleted,
 *                           portsRefreshed, audioDevicesReady)
 *   appBridge : AppBridge
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── État local ───────────────────────────────────────────────────────────
    property real   freq:       0.0
    property string radioMode:  "---"
    property bool   connected:  false
    property real   smeter:     0.0
    property int    preamp:     1
    property bool   att:        false
    property int    ifFilter:   2
    property bool   scanning:   false

    // Listes dynamiques
    property var portsList:    ["COM14", "COM5", "COM3"]
    property var audioDevList: ["IC-705 USB Audio"]
    property var scanResults:  []

    // Préférences de connexion
    property string selPort:    "COM14"
    property int    selBaud:    19200
    property string selProto:   "ICOM CI-V"
    property string selCiv:     "A4"
    property string selAudio:   ""

    // ── Connexion aux ponts ──────────────────────────────────────────────────
    Connections {
        target: radio
        function onFreqChanged(hz)       { root.freq = hz }
        function onModeChanged(mode)     { root.radioMode = mode }
        function onHandshakeChanged(ok)  { root.connected = ok }
        function onSmeterChanged(level)  { root.smeter = level }
        function onLogMessage(text)      { radioLog.append(text) }
        function onPreampChanged(level)  { root.preamp = level }
        function onAttChanged(on)        { root.att = on }
        function onFilterChanged(f)      { root.ifFilter = f }
        function onScanProgress(id, snr) {
            root.scanning = true
            radioLog.append("  → " + id + " : " + snr.toFixed(1) + " dB")
        }
        function onScanCompleted(results) {
            root.scanning = false
            root.scanResults = results
            radioLog.append("✅ Scan terminé — " + results.length + " stations.")
        }
        function onPortsRefreshed(ports)  { root.portsList = ports }
        function onAudioDevicesReady(devs) { root.audioDevList = devs }
    }

    // ── Initialisation ───────────────────────────────────────────────────────
    Component.onCompleted: {
        radio.refreshPorts()
        radio.refreshAudioDevices()
    }

    // ── Mise en page principale ──────────────────────────────────────────────
    RowLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ══════════════════════════════════════════════════════════════════
        // PANNEAU GAUCHE : configuration + commandes
        // ══════════════════════════════════════════════════════════════════
        ColumnLayout {
            Layout.preferredWidth: 310
            Layout.fillHeight: true
            spacing: T.Theme.spacing

            // ── Affichage fréquence + mode + CI-V ─────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: 80
                color:  T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: root.connected ? T.Theme.borderActive : T.Theme.border

                RowLayout {
                    anchors { fill: parent; margins: T.Theme.spacing }
                    spacing: T.Theme.spacing

                    Column {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            text: {
                                if (root.freq <= 0) return "--- . --- . ---"
                                const mhz = (root.freq / 1e6).toFixed(6)
                                const p   = mhz.split(".")
                                return p[0] + "." + p[1].substring(0,3) + "." + p[1].substring(3)
                            }
                            color: T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: 22
                            font.bold: true
                        }
                        Text {
                            text: "MHz  |  " + root.radioMode
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                        }
                    }

                    // Badge CI-V
                    Rectangle {
                        width: 72; height: 24
                        radius: 12
                        color: root.connected ? T.Theme.okBg : T.Theme.errBg

                        Text {
                            anchors.centerIn: parent
                            text: root.connected ? "CI-V OK" : "HORS-LIGNE"
                            color: root.connected ? T.Theme.okFg : T.Theme.errFg
                            font.family: T.Theme.fontMono
                            font.pixelSize: 9
                            font.bold: true
                        }
                    }
                }
            }

            // ── S-mètre ───────────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: 60
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                Column {
                    anchors { fill: parent; margins: T.Theme.spacing }
                    spacing: 4

                    Text {
                        text: "S-MÈTRE"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        font.letterSpacing: 1
                    }
                    C.SMeter {
                        width:  parent.width - 2
                        level:  root.smeter
                    }
                }
            }

            // ── Section : Connexion CAT ───────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border
                height: connColLayout.implicitHeight + 16

                ColumnLayout {
                    id: connColLayout
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6

                    Text {
                        text: "CONNEXION CAT"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        font.letterSpacing: 1
                    }

                    // Protocole
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Modèle :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 65 }
                        C.DropDown {
                            Layout.fillWidth: true
                            model: ["ICOM CI-V", "YAESU CAT", "AUTO"]
                            currentText: root.selProto
                            onSelected: (txt) => root.selProto = txt
                        }
                    }

                    // Port + Baud + CI-V
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Port :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 40 }
                        C.DropDown {
                            Layout.preferredWidth: 90
                            model: root.portsList
                            currentText: root.selPort
                            onSelected: (txt) => root.selPort = txt
                        }
                        // Rafraîchir
                        C.FlatButton { text: "🔄"; accent: false; implicitWidth: 30; onClicked: radio.refreshPorts() }

                        Text { text: "Baud :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                        C.DropDown {
                            Layout.preferredWidth: 80
                            model: ["4800", "9600", "19200", "38400", "115200"]
                            currentText: String(root.selBaud)
                            onSelected: (txt) => root.selBaud = parseInt(txt)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "CI-V :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 40 }
                        C.TextInput { id: civInput; Layout.preferredWidth: 60; text: root.selCiv; onTextChanged: root.selCiv = text; fontFamily: T.Theme.fontMono }
                        Item { Layout.fillWidth: true }
                    }

                    // Boutons connexion
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: T.Theme.spacing

                        C.FlatButton {
                            text:    "▶ AUTO"
                            accent:  true
                            Layout.fillWidth: true
                            onClicked: {
                                radioLog.append("▶ Auto-détection…")
                                radio.autoDetect()
                            }
                        }
                        C.FlatButton {
                            text:    root.connected ? "Déconnecter" : "Connecter"
                            accent:  !root.connected
                            Layout.fillWidth: true
                            onClicked: {
                                if (root.connected)
                                    radio.disconnect()
                                else
                                    radio.connectFull(root.selPort, root.selBaud, root.selProto, root.selCiv)
                            }
                        }
                    }
                }
            }

            // ── Section : Audio USB ───────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border
                height: audioColLayout.implicitHeight + 16

                ColumnLayout {
                    id: audioColLayout
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6

                    Text {
                        text: "AUDIO RX"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        font.letterSpacing: 1
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        C.DropDown {
                            Layout.fillWidth: true
                            model: root.audioDevList
                            currentText: root.selAudio || (root.audioDevList.length > 0 ? root.audioDevList[0] : "")
                            onSelected: (txt) => root.selAudio = txt
                        }
                        C.FlatButton { text: "🔄"; accent: false; implicitWidth: 30; onClicked: radio.refreshAudioDevices() }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        C.FlatButton {
                            text:    "▶ Démarrer Audio"
                            accent:  true
                            Layout.fillWidth: true
                            onClicked: appBridge.startAudio(root.selAudio, 44100)
                        }
                        C.FlatButton {
                            text:    "⏹ Arrêter"
                            accent:  false
                            Layout.fillWidth: true
                            onClicked: appBridge.stopAudio()
                        }
                    }
                }
            }

            // ── Section : RF (Préampli + Atténuateur + Filtre FI) ─────────
            Rectangle {
                Layout.fillWidth: true
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border
                height: rfColLayout.implicitHeight + 16

                ColumnLayout {
                    id: rfColLayout
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6

                    Text {
                        text: "ÉTAGE RF & FILTRE FI IC-705"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        font.letterSpacing: 1
                    }

                    // Préampli (3 boutons segmentés)
                    Text { text: "Préampli HF :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater {
                            model: [{ val: 0, lbl: "IPO" }, { val: 1, lbl: "PAMP1" }, { val: 2, lbl: "PAMP2" }]
                            delegate: C.FlatButton {
                                property int pVal: modelData.val
                                text:    modelData.lbl
                                accent:  root.preamp === pVal
                                Layout.fillWidth: true
                                onClicked: radio.setPreamp(pVal)
                            }
                        }
                    }

                    // Filtre FI
                    Text { text: "Filtre FI USB-D :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater {
                            model: [{ val: 1, lbl: "FIL1 3.0k" }, { val: 2, lbl: "FIL2 2.4k" }, { val: 3, lbl: "FIL3 Étroit" }]
                            delegate: C.FlatButton {
                                property int fVal: modelData.val
                                text:    modelData.lbl
                                accent:  root.ifFilter === fVal
                                Layout.fillWidth: true
                                onClicked: radio.setIFFilter(fVal)
                            }
                        }
                    }

                    // Atténuateur
                    RowLayout {
                        Layout.fillWidth: true
                        C.FlatButton {
                            text:    root.att ? "ATTÉNUATEUR ON" : "ATTÉNUATEUR OFF"
                            accent:  root.att
                            Layout.fillWidth: true
                            onClicked: radio.setAttenuator(!root.att)
                        }
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }

        // ══════════════════════════════════════════════════════════════════
        // PANNEAU DROIT : scan + liste stations + log
        // ══════════════════════════════════════════════════════════════════
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: T.Theme.spacing

            // ── Scan + résultats ──────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: 240
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                ColumnLayout {
                    anchors { fill: parent; margins: T.Theme.spacing }
                    spacing: T.Theme.spacing

                    // En-tête scan
                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            text: "STATIONS WEFAX (7 ÉMETTEURS)"
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                            font.letterSpacing: 1
                        }

                        Item { Layout.fillWidth: true }

                        C.FlatButton {
                            text:    root.scanning ? "⏳ Scan…" : "▶ SCANNER"
                            accent:  true
                            enabled: root.connected && !root.scanning
                            onClicked: radio.scanFrequencies()
                        }

                        C.FlatButton {
                            text:    "📋 Résultats"
                            accent:  false
                            enabled: root.scanResults.length > 0
                            onClicked: scanPopup.open()
                        }
                    }

                    // En-têtes colonnes
                    Rectangle {
                        Layout.fillWidth: true
                        height: 22
                        color: T.Theme.bgSurface
                        radius: T.Theme.radiusSm

                        RowLayout {
                            anchors { fill: parent; leftMargin: 6; rightMargin: 6 }
                            spacing: 0

                            component Hdr: Text {
                                property int cw: 80
                                Layout.preferredWidth: cw
                                color: T.Theme.textDim
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeXs
                            }
                            Hdr { text: "INDIC.";   cw: 60 }
                            Hdr { text: "STATION";  cw: 160; Layout.fillWidth: true }
                            Hdr { text: "PORTEUSE"; cw: 80 }
                            Hdr { text: "OPTIMUM";  cw: 70 }
                            Hdr { text: "SNR";      cw: 70 }
                            Hdr { text: "";         cw: 60 }
                        }
                    }

                    // Liste stations
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        model: stationsModel
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 28
                            color: index % 2 === 0 ? "transparent" : Qt.rgba(1,1,1,0.03)

                            HoverHandler { id: rowH }
                            Rectangle {
                                anchors.fill: parent; color: "white"
                                opacity: rowH.hovered ? 0.05 : 0
                                Behavior on opacity { NumberAnimation { duration: 80 } }
                            }

                            RowLayout {
                                anchors { fill: parent; leftMargin: 6; rightMargin: 6 }
                                spacing: 0

                                component Cell: Text {
                                    property int cw: 80
                                    Layout.preferredWidth: cw
                                    color: T.Theme.textMuted
                                    font.family: T.Theme.fontMono
                                    font.pixelSize: T.Theme.fontSizeSm
                                    elide: Text.ElideRight
                                }

                                Cell { text: model.code;    cw: 60; color: T.Theme.accentLight; font.bold: true }
                                Cell { text: model.station; Layout.fillWidth: true }
                                Cell { text: model.freq + " kHz"; cw: 80 }
                                Cell { text: model.period;        cw: 70 }
                                Cell {
                                    text: model.snrText || "---"; cw: 70
                                    color: model.snr >= 10 ? T.Theme.okFg : (model.snr >= 5 ? T.Theme.warnFg : T.Theme.textDim)
                                }

                                C.FlatButton {
                                    text:    "QSY"
                                    accent:  true
                                    enabled: root.connected
                                    implicitWidth:  52
                                    implicitHeight: 20
                                    Layout.preferredWidth: 52
                                    onClicked: {
                                        radio.tuneStation(model.freq)
                                        radioLog.append("QSY → " + model.code + " " + model.freq + " kHz")
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Mode d'exploitation ───────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: 60
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                RowLayout {
                    anchors { fill: parent; margins: T.Theme.spacing }
                    spacing: T.Theme.spacing

                    Text {
                        text: "MODE :"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        font.letterSpacing: 1
                    }

                    Repeater {
                        model: ["WEFAX", "RTTY", "HYBRIDE", "MANUEL"]
                        delegate: C.FlatButton {
                            property string mVal: modelData
                            text:    modelData
                            accent:  appBridge.currentMode === mVal
                            Layout.fillWidth: true
                            onClicked: appBridge.setMode(mVal)
                        }
                    }
                }
            }

            // ── Log radio ─────────────────────────────────────────────────
            C.LogView {
                id: radioLog
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }
    }

    // ── Modèle stations (depuis core/stations.py via appBridge) ─────────────
    ListModel {
        id: stationsModel
        ListElement { code: "DDH3";  station: "DWD Pinneberg";  freq: 3855.0;   period: "NUIT";      snr: -99; snrText: "---" }
        ListElement { code: "DDK3";  station: "DWD Pinneberg";  freq: 7880.0;   period: "JOUR/NUIT"; snr: -99; snrText: "---" }
        ListElement { code: "DDK6";  station: "DWD Pinneberg";  freq: 13882.5;  period: "JOUR";      snr: -99; snrText: "---" }
        ListElement { code: "GYA1";  station: "Northwood UK";   freq: 2618.5;   period: "NUIT";      snr: -99; snrText: "---" }
        ListElement { code: "GYA2";  station: "Northwood UK";   freq: 4610.0;   period: "NUIT";      snr: -99; snrText: "---" }
        ListElement { code: "GYA3";  station: "Northwood UK";   freq: 8040.0;   period: "JOUR/NUIT"; snr: -99; snrText: "---" }
        ListElement { code: "GYA4";  station: "Northwood UK";   freq: 11086.5;  period: "JOUR";      snr: -99; snrText: "---" }
    }

    // Mise à jour du modèle quand le scan est terminé
    onScanResultsChanged: {
        for (let r of scanResults) {
            for (let i = 0; i < stationsModel.count; i++) {
                if (stationsModel.get(i).code === r.code) {
                    stationsModel.setProperty(i, "snr",     r.snr)
                    stationsModel.setProperty(i, "snrText", r.snrText)
                }
            }
        }
    }

    // ── Pop-up résultats scan ─────────────────────────────────────────────
    // (réutilise scanResults directement depuis la liste)
}
