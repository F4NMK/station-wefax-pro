import QtQuick
import QtQuick.Layouts

/*
 * TabBar.qml — Barre d'onglets horizontale style "instrumentation"
 *
 * Usage :
 *   TabBar {
 *       model: ["RADIO", "IMAGE", "MÉTÉO", "PLAN"]
 *       currentIndex: 0
 *       onCurrentIndexChanged: stack.currentIndex = currentIndex
 *   }
 */
Rectangle {
    id: root

    property var    model:        []
    property int    currentIndex: 0
    property color  bgColor:      "#1b2430"
    property color  borderColor:  "#2e3d4f"
    property color  accentColor:  "#2563eb"
    property color  textActive:   "#e6edf3"
    property color  textInactive: "#64748b"
    property string fontFamily:   "Segoe UI, Ubuntu, sans-serif"
    property int    fontSizePx:   11

    signal currentIndexChanged(int index)

    height: 38
    color: bgColor

    // Bordure basse
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width; height: 1
        color: borderColor
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 4

        Repeater {
            model: root.model

            delegate: Item {
                width: tabText.implicitWidth + 32
                height: root.height

                readonly property bool active: index === root.currentIndex

                // Indicateur actif (bas de l'onglet)
                Rectangle {
                    visible: active
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 8; height: 2
                    color: root.accentColor
                    radius: 1
                }

                Text {
                    id: tabText
                    anchors.centerIn: parent
                    text: modelData
                    color: active ? root.textActive : root.textInactive
                    font.family: root.fontFamily
                    font.pixelSize: root.fontSizePx
                    font.bold: active
                    font.letterSpacing: 0.5
                }

                TapHandler {
                    onTapped: {
                        root.currentIndex = index
                        root.currentIndexChanged(index)
                    }
                }

                HoverHandler { id: hov }

                // Survol : légère surbrillance
                Rectangle {
                    anchors.fill: parent
                    color: "white"
                    opacity: hov.hovered && !active ? 0.04 : 0
                    Behavior on opacity { NumberAnimation { duration: 100 } }
                }
            }
        }
    }
}
