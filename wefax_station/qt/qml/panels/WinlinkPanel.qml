import QtQuick
import QtQuick.Layouts
import "../components" as C
import ".." as T

/*
 * WinlinkPanel.qml — Onglet WINLINK
 *
 * Recrée WinlinkDeskMixin (Tkinter) :
 *   - Session Winlink/VARA vers un gateway
 *   - Envoi d'image WEFAX (conversion JPEG automatique)
 *   - Demande GRIB (Saildocs)
 *   - Enregistrement audio brut
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── État local ───────────────────────────────────────────────────────────
    property bool   sessionOpen:      false
    property bool   recording:        false
    property string recordingPath:    ""
    property string lastImagePath:    ""
    property string winlinkStatus:    "Aucune session active"
    property string gateway:          "F5LEN-10"
    property int    gatewayPort:      8772

    // ── Connexions aux ponts ─────────────────────────────────────────────────
    Connections {
        target: appBridge
        function onWinlinkStatus(msg) { root.winlinkStatus = msg; winlinkLog.append(msg) }
        function onWinlinkSessionStarted() { root.sessionOpen = true }
        function onWinlinkSessionStopped() { root.sessionOpen = false }
        function onRecordingStarted(path) { root.recording = true; root.recordingPath = path; winlinkLog.append("⏺ Enregistrement : " + path) }
        function onRecordingStopped(path) { root.recording = false; winlinkLog.append("⏹ Enregistrement terminé : " + path) }
        function onJournalLine(line) {
            if (line.indexOf("Winlink") >= 0 || line.indexOf("JPEG") >= 0 ||
                line.indexOf("Enreg") >= 0 || line.indexOf("GRIB") >= 0)
                winlinkLog.append(line)
        }
    }

    // Réception du chemin image courant depuis ImagePanel
    Connections {
        target: appBridge
        function onStatusChanged(msg) {
            if (msg.startsWith("Image reçue : ")) {
                // On ne peut pas récupérer le chemin complet ici — l'image est dans le dossier archive
                root.lastImagePath = ""   // sera mis à jour par imageCompleted
            }
        }
    }

    // ── Mise en page ─────────────────────────────────────────────────────────
    RowLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ── Panneau gauche : contrôles ────────────────────────────────────
        ColumnLayout {
            Layout.preferredWidth: 260
            Layout.fillHeight: true
            spacing: T.Theme.spacing

            // ── Session Winlink ──────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: sessionCol.implicitHeight + 16
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: root.sessionOpen ? T.Theme.accentBorder : T.Theme.border

                ColumnLayout {
                    id: sessionCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    spacing: 8

                    Text { text: "SESSION WINLINK"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Gateway :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 70 }
                        C.TextInput {
                            Layout.fillWidth: true
                            text: root.gateway
                            placeholder: "F5LEN-10"
                            fontFamily: T.Theme.fontMono
                            onTextChanged: root.gateway = text
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Port :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 70 }
                        C.DropDown {
                            model: ["8772", "8778"]
                            currentText: String(root.gatewayPort)
                            onSelected: (txt) => root.gatewayPort = parseInt(txt)
                        }
                    }

                    // Statut session
                    Rectangle {
                        Layout.fillWidth: true
                        height: 28
                        radius: T.Theme.radiusSm
                        color: root.sessionOpen ? Qt.rgba(0.1, 0.8, 0.3, 0.1) : T.Theme.bgSurface
                        border.color: root.sessionOpen ? "#2ecc71" : T.Theme.border

                        Text {
                            anchors.centerIn: parent
                            text: root.sessionOpen ? "🟢 Session ouverte" : "⚫ Aucune session"
                            color: root.sessionOpen ? "#2ecc71" : T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        C.FlatButton {
                            text: root.sessionOpen ? "🔌 Fermer" : "🌐 Ouvrir"
                            accent: !root.sessionOpen
                            Layout.fillWidth: true
                            onClicked: {
                                if (root.sessionOpen)
                                    appBridge.closeWinlinkSession()
                                else
                                    appBridge.openWinlinkSession(root.gateway, root.gatewayPort)
                            }
                        }
                    }
                }
            }

            // ── Envoi image ──────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: imgCol.implicitHeight + 16
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                ColumnLayout {
                    id: imgCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    spacing: 8

                    Text { text: "ENVOI IMAGE WEFAX"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    Text {
                        Layout.fillWidth: true
                        text: "Le format JPEG (~40–80 kB) est configuré\ndans Paramètres → DSP & Réception."
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        wrapMode: Text.WordWrap
                        lineHeight: 1.3
                    }

                    C.FlatButton {
                        text: "📤 Préparer image pour Winlink"
                        Layout.fillWidth: true
                        accent: false
                        enabled: root.lastImagePath !== ""
                        onClicked: appBridge.sendWinlinkImage(root.lastImagePath)
                    }

                    Text {
                        visible: root.lastImagePath === ""
                        text: "⚠ Aucune image reçue dans cette session"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // ── GRIB Saildocs ────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: gribCol.implicitHeight + 16
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                ColumnLayout {
                    id: gribCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    spacing: 8

                    Text { text: "MÉTÉO GRIB (SAILDOCS)"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    C.FlatButton {
                        text: "📥 Demander GRIB"
                        Layout.fillWidth: true
                        accent: false
                        onClicked: appBridge.requestGrib()
                    }
                }
            }

            // ── Enregistrement audio ─────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: recCol.implicitHeight + 16
                color: T.Theme.bgPanel
                radius: root.recording ? T.Theme.radiusMd : T.Theme.radiusMd
                border.color: root.recording ? "#e74c3c" : T.Theme.border

                ColumnLayout {
                    id: recCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    spacing: 8

                    Text { text: "ENREGISTREMENT AUDIO"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 28
                        radius: T.Theme.radiusSm
                        color: root.recording ? Qt.rgba(0.9, 0.2, 0.1, 0.1) : T.Theme.bgSurface
                        border.color: root.recording ? "#e74c3c" : T.Theme.border

                        Row {
                            anchors.centerIn: parent
                            spacing: 6

                            Rectangle {
                                visible: root.recording
                                width: 8; height: 8; radius: 4
                                color: "#e74c3c"
                                SequentialAnimation on opacity {
                                    running: root.recording
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0; duration: 500 }
                                    NumberAnimation { to: 1; duration: 500 }
                                }
                            }

                            Text {
                                text: root.recording ? "EN COURS" : "ARRÊTÉ"
                                color: root.recording ? "#e74c3c" : T.Theme.textDim
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeSm
                                font.bold: root.recording
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        C.FlatButton {
                            text: "⏺ Démarrer"
                            accent: false
                            Layout.fillWidth: true
                            enabled: !root.recording
                            onClicked: appBridge.startRecording()
                        }
                        C.FlatButton {
                            text: "⏹ Arrêter"
                            accent: false
                            Layout.fillWidth: true
                            enabled: root.recording
                            onClicked: appBridge.stopRecording()
                        }
                    }

                    C.FlatButton {
                        text: "📂 Dossier enregistrements"
                        Layout.fillWidth: true
                        accent: false
                        onClicked: appBridge.openRecordings()
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }

        // ── Panneau droit : log ──────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: T.Theme.spacing

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                ColumnLayout {
                    anchors { fill: parent; margins: T.Theme.spacing }
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "JOURNAL WINLINK"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1; Layout.fillWidth: true }
                        C.FlatButton { text: "🗑 Vider"; accent: false; implicitWidth: 80; onClicked: winlinkLog.clear() }
                    }

                    // Statut en temps réel
                    Rectangle {
                        Layout.fillWidth: true
                        height: 32
                        radius: T.Theme.radiusSm
                        color: T.Theme.bgSurface
                        border.color: T.Theme.border

                        Text {
                            anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
                            text: root.winlinkStatus
                            color: T.Theme.textMuted
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            elide: Text.ElideRight
                            width: parent.width - 20
                        }
                    }

                    C.LogView {
                        id: winlinkLog
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                    }
                }
            }
        }
    }
}
