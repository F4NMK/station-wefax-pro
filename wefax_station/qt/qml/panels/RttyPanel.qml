import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../components" as C
import ".." as T

/*
 * RttyPanel.qml — Onglet RTTY / NAVTEX (téléimprimeur)
 *
 * Recrée le TeleprinterPanelMixin Tkinter :
 *   - texte Consolas ambre sur fond sombre
 *   - barre de statut avec indicateurs RTTY / NAVTEX / BAUD
 *   - contrôles : effacer, sauvegarder, filtre stations NAVTEX
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── État local ───────────────────────────────────────────────────────────
    property bool   rttyActive:   false
    property bool   navtexActive: false
    property string currentStation: ""
    property string currentBaud:    "50"
    property int    shift:          450      // Hz, standard RTTY
    property string navtexFilter:   ""       // Lettre station (B1, L2, …) ou ""
    property bool   autoStart:      false
    property var    textBuffer:     []

    // ── Connexion aux ponts ──────────────────────────────────────────────────
    Connections {
        target: appBridge
        function onRttyLine(text, station) {
            appendLine(text, station)
            if (!root.rttyActive) root.rttyActive = true
            root.currentStation = station
        }
        function onNavtexLine(text, station) {
            appendLine("[NAVTEX " + station + "] " + text, station)
            if (!root.navtexActive) root.navtexActive = true
        }
        function onModeChanged(mode) {
            root.rttyActive   = (mode === "RTTY" || mode === "HYBRIDE")
            root.navtexActive = (mode === "NAVTEX")
        }
    }

    // ── Fonctions locales ────────────────────────────────────────────────────
    function appendLine(text, station) {
        if (root.navtexFilter !== "" && station && !station.includes(root.navtexFilter))
            return
        const ts = Qt.formatTime(new Date(), "HH:mm:ss")
        teleText.append({time: ts, line: text})
        // Auto-scroll
        teleView.positionViewAtEnd()
    }

    function clearTeletypewriter() {
        teleText.clear()
        root.rttyActive = false
    }

    // ── Mise en page principale ──────────────────────────────────────────────
    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacing

        // ── Barre de statut ───────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: T.Theme.spacing

            // Indicateur RTTY
            Rectangle {
                width: 100; height: 36
                radius: T.Theme.radiusMd
                color: T.Theme.bgPanel
                border.color: root.rttyActive ? T.Theme.accentBorder : T.Theme.border

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Rectangle {
                        width: 8; height: 8; radius: 4
                        color: root.rttyActive ? T.Theme.accent : T.Theme.textDim
                        anchors.verticalCenter: parent.verticalCenter

                        // Clignote si actif
                        SequentialAnimation on opacity {
                            running: root.rttyActive
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.2; duration: 400 }
                            NumberAnimation { to: 1.0; duration: 400 }
                        }
                    }
                    Text {
                        text: "RTTY"
                        color: root.rttyActive ? T.Theme.accent : T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeSm
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            // Indicateur NAVTEX
            Rectangle {
                width: 100; height: 36
                radius: T.Theme.radiusMd
                color: T.Theme.bgPanel
                border.color: root.navtexActive ? "#c084fc" : T.Theme.border

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Rectangle {
                        width: 8; height: 8; radius: 4
                        color: root.navtexActive ? "#c084fc" : T.Theme.textDim
                        anchors.verticalCenter: parent.verticalCenter

                        SequentialAnimation on opacity {
                            running: root.navtexActive
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.2; duration: 600 }
                            NumberAnimation { to: 1.0; duration: 600 }
                        }
                    }
                    Text {
                        text: "NAVTEX"
                        color: root.navtexActive ? "#c084fc" : T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeSm
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            // Vitesse + shift
            Rectangle {
                width: 160; height: 36
                radius: T.Theme.radiusMd
                color: T.Theme.bgPanel
                border.color: T.Theme.border

                Row {
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        text: root.currentBaud + " Bd"
                        color: T.Theme.textPrimary
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeSm
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "Δ " + root.shift + " Hz"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            // Station courante
            Rectangle {
                Layout.fillWidth: true
                height: 36
                radius: T.Theme.radiusMd
                color: T.Theme.bgPanel
                border.color: T.Theme.border

                Text {
                    anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
                    text: root.currentStation !== "" ? "Station : " + root.currentStation : "Pas de réception"
                    color: root.currentStation !== "" ? T.Theme.textPrimary : T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeSm
                }
            }
        }

        // ── Contrôles ─────────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: T.Theme.spacing

            // Vitesse RTTY
            Text { text: "Vitesse :"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
            C.DropDown {
                model: ["45", "50", "75", "100", "150"]
                currentText: root.currentBaud
                onSelected: (txt) => { root.currentBaud = txt; appBridge.setRttyBaud(parseInt(txt)) }
            }

            // Shift
            Text { text: "Shift :"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
            C.DropDown {
                model: ["170", "425", "450", "850"]
                currentText: String(root.shift)
                onSelected: (txt) => { root.shift = parseInt(txt); appBridge.setRttyShift(parseInt(txt)) }
            }

            // Filtre NAVTEX
            Text { text: "Filtre NAVTEX :"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
            C.TextInput {
                implicitWidth: 60
                text: root.navtexFilter
                placeholder: "tous"
                fontFamily: T.Theme.fontMono
                onTextChanged: root.navtexFilter = text.toUpperCase()
            }

            Item { Layout.fillWidth: true }

            // Auto-démarrage
            C.FlatButton {
                text: root.autoStart ? "✅ AUTO-START" : "AUTO-START"
                accent: root.autoStart
                onClicked: root.autoStart = !root.autoStart
            }

            C.FlatButton {
                text: "💾 Sauvegarder"
                accent: false
                enabled: teleText.count > 0
                onClicked: appBridge.saveRttyLog()
            }

            C.FlatButton {
                text: "🗑 Effacer"
                accent: false
                onClicked: clearTeletypewriter()
            }
        }

        // ── Téléimprimeur ─────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0d1117"      // Fond très sombre style TTY
            radius: T.Theme.radiusMd
            border.color: "#2a3444"
            clip: true

            // Scan line subtil pour l'ambiance CRT
            Rectangle {
                anchors.fill: parent
                visible: true
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.rgba(1,1,1,0.01) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            ListView {
                id: teleView
                anchors { fill: parent; margins: 12 }
                model: ListModel { id: teleText }
                clip: true
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Row {
                    spacing: 10

                    Text {
                        text: model.time
                        color: "#4a5568"
                        font.family: T.Theme.fontMono
                        font.pixelSize: 11
                    }
                    Text {
                        text: model.line
                        color: "#ffa500"      // Ambre — style TTY
                        font.family: T.Theme.fontMono
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                        width: teleView.width - 70
                    }
                }

                // Curseur clignotant si actif
                Rectangle {
                    x:       0
                    y:       teleView.contentHeight
                    width:   8
                    height:  14
                    color:   "#ffa500"
                    visible: root.rttyActive || root.navtexActive

                    SequentialAnimation on opacity {
                        running: root.rttyActive || root.navtexActive
                        loops: Animation.Infinite
                        NumberAnimation { to: 0; duration: 500 }
                        NumberAnimation { to: 1; duration: 500 }
                    }
                }

                // Placeholder
                Text {
                    anchors.centerIn: parent
                    visible: teleText.count === 0
                    text: "Téléimprimeur RTTY / NAVTEX\n\n" +
                          "En attente de signal…\n" +
                          "Sélectionnez RTTY ou HYBRIDE\n" +
                          "dans l'onglet RADIO."
                    color: "#2a3444"
                    font.family: T.Theme.fontMono
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
