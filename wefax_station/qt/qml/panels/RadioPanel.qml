import QtQuick
import QtQuick.Layouts
import "../components" as C
import ".." as T

/*
 * RadioPanel.qml — Onglet RADIO
 *
 * Context properties attendus :
 *   radio  : RadioBridge  (signaux freqChanged, modeChanged, handshakeChanged, smeterChanged, logMessage)
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── Fréquence courante ───────────────────────────────────────────────
    property real   freq:       0.0
    property string radioMode:  "---"
    property bool   connected:  false
    property real   smeter:     0.0   // 0.0 = silence, 1.0 = S9+60

    Connections {
        target: radio
        function onFreqChanged(hz)       { root.freq = hz }
        function onModeChanged(mode)     { root.radioMode = mode }
        function onHandshakeChanged(ok)  { root.connected = ok }
        function onSmeterChanged(level)  { root.smeter = level }
        function onLogMessage(text)      { radioLog.append(text) }
    }

    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ── Ligne supérieure : fréquence + statut liaison ────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: T.Theme.spacingLg

            // Affichage grande fréquence
            Rectangle {
                Layout.preferredWidth: 260
                height: 72
                color:  T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: root.connected ? T.Theme.borderActive : T.Theme.border

                Column {
                    anchors.centerIn: parent
                    spacing: 2

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: {
                            if (root.freq <= 0) return "--- . --- . ---"
                            const mhz = (root.freq / 1e6).toFixed(6)
                            const parts = mhz.split(".")
                            return parts[0] + "." + parts[1].substring(0,3) + "." + parts[1].substring(3)
                        }
                        color: T.Theme.textPrimary
                        font.family: T.Theme.fontMono
                        font.pixelSize: 26
                        font.bold: true
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "MHz"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeSm
                    }
                }
            }

            // Mode + handshake
            Rectangle {
                Layout.preferredWidth: 100
                height: 72
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                Column {
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.radioMode
                        color: T.Theme.textPrimary
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeLg
                        font.bold: true
                    }

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 60; height: 18
                        radius: 9
                        color: root.connected ? T.Theme.okBg : T.Theme.errBg

                        Text {
                            anchors.centerIn: parent
                            text: root.connected ? "CI-V OK" : "HORS-LIGNE"
                            color: root.connected ? T.Theme.okFg : T.Theme.errFg
                            font.family: T.Theme.fontMono
                            font.pixelSize: 8
                            font.bold: true
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // Boutons connexion / déconnexion
            Column {
                spacing: T.Theme.spacing

                C.FlatButton {
                    text:    "Connecter IC-705"
                    enabled: !root.connected
                    accent:  true
                    onClicked: radio.connect("COM14", 19200)
                }

                C.FlatButton {
                    text:    "Déconnecter"
                    enabled: root.connected
                    accent:  false
                    onClicked: radio.disconnect()
                }
            }
        }

        // ── S-mètre ──────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 70
            color:  T.Theme.bgPanel
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

        // ── Log radio ────────────────────────────────────────────────────
        C.LogView {
            id: radioLog
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
