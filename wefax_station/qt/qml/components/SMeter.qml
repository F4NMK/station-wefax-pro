import QtQuick
import QtQuick.Layouts
import ".." as T

/*
 * SMeter.qml — Bargraphe S-mètre style rétro
 *
 * Propriétés :
 *   level    : float 0.0–1.0  (0 = S0, 1 = S9+60)
 *   dbValue  : float en dBm   (affiché en texte si ≠ 0)
 */
Item {
    id: root

    property real   level:   0.0
    property real   dbValue: 0.0

    implicitWidth:  220
    implicitHeight: 48

    // Graduations : S1 S2 … S9 +20 +40 +60
    readonly property var labels: ["S1","S2","S3","S4","S5","S6","S7","S8","S9","+20","+40","+60"]

    Column {
        anchors.fill: parent
        spacing: 4

        // ── Bargraphe ──────────────────────────────────────────────────
        Rectangle {
            width: parent.width; height: 20
            color: T.Theme.bgCanvas
            radius: 3
            clip: true

            // Segments colorés (12)
            Row {
                anchors { fill: parent; margins: 2 }
                spacing: 2

                Repeater {
                    model: 12
                    delegate: Rectangle {
                        readonly property real segThreshold: (index + 1) / 12.0
                        readonly property bool lit: root.level >= segThreshold - (1/12.0 * 0.5)

                        // S1–S5 vert, S6–S9 orange, +xx rouge
                        readonly property color segColor: {
                            if (index < 5)  return "#15803d"
                            if (index < 9)  return "#b45309"
                            return "#b91c1c"
                        }

                        height: parent.height
                        width:  (parent.width - 11 * 2) / 12   // 12 segments, 11 gaps
                        color:  lit ? segColor : Qt.darker(segColor, 3.5)
                        radius: 2

                        Behavior on color { ColorAnimation { duration: 60 } }
                    }
                }
            }
        }

        // ── Étiquettes S1-S9+60 ───────────────────────────────────────
        Row {
            width: parent.width
            spacing: 0

            Repeater {
                model: root.labels
                delegate: Text {
                    width:  (parent.width) / root.labels.length
                    text:   modelData
                    color:  T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: 7
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
