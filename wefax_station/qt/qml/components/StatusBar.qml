import QtQuick
import QtQuick.Layouts
import ".." as T

/*
 * StatusBar.qml — Barre de statut inférieure
 * Propriétés exposées : statusText, modeText, mode, audioConnected
 */
Rectangle {
    id: root

    property string statusText:     "En attente…"
    property string modeText:       "IDLE"
    property string mode:           "IDLE"
    property bool   audioConnected: false

    height: 26
    color:  T.Theme.bgOverlay

    RowLayout {
        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
        spacing: 12

        // ── Pastille mode ───────────────────────────────────────────────
        Rectangle {
            width: 10; height: 10
            radius: 5
            color: T.Theme.modeColor(root.mode)
        }

        Text {
            text: root.modeText
            color: T.Theme.textPrimary
            font.family: T.Theme.fontMono
            font.pixelSize: T.Theme.fontSizeSm
            font.bold: true
        }

        // ── Séparateur ──────────────────────────────────────────────────
        Rectangle { width: 1; height: 16; color: T.Theme.border }

        // ── Texte statut principal ──────────────────────────────────────
        Text {
            Layout.fillWidth: true
            text: root.statusText
            color: T.Theme.textMuted
            font.family: T.Theme.fontMono
            font.pixelSize: T.Theme.fontSizeSm
            elide: Text.ElideRight
        }

        // ── Indicateur audio ────────────────────────────────────────────
        Rectangle {
            width: 8; height: 8
            radius: 4
            color: root.audioConnected ? T.Theme.okBg : T.Theme.errBg

            ToolTip.visible: audioHover.containsMouse
            ToolTip.text:    root.audioConnected ? "Audio connecté" : "Audio déconnecté"

            HoverHandler { id: audioHover }
        }

        Text {
            text: "AUDIO"
            color: T.Theme.textDim
            font.family: T.Theme.fontMono
            font.pixelSize: T.Theme.fontSizeXs
        }
    }
}
