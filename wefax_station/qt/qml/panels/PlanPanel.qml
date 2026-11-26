import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../components" as C
import ".." as T

/*
 * PlanPanel.qml — Onglet PLAN (programme de réception)
 *
 * Context property attendu : appBridge (AppBridge)
 * Signal appBridge.scheduleChanged() déclenche la mise à jour de la grille.
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // Modèle de grille — alimenté par AppBridge.getSchedule() (à implémenter)
    ListModel { id: scheduleModel }

    Connections {
        target: appBridge
        function onScheduleChanged() {
            // TODO : appBridge.getSchedule() retournera une liste de dicts :
            // { time, source, freq_mhz, mode, duration_min, status }
            // scheduleModel.clear()
            // for each entry: scheduleModel.append(entry)
        }
    }

    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ── En-tête + bouton actualiser ────────────────────────────────
        RowLayout {
            Layout.fillWidth: true

            Text {
                text: "PROGRAMME DE RÉCEPTION"
                color: T.Theme.textDim
                font.family: T.Theme.fontMono
                font.pixelSize: T.Theme.fontSizeXs
                font.letterSpacing: 2
            }

            Item { Layout.fillWidth: true }

            C.FlatButton {
                text:   "Actualiser"
                accent: true
                onClicked: appBridge.requestScheduleRefresh()
            }
        }

        // ── En-têtes de colonne ────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 28
            color: T.Theme.bgSurface
            radius: T.Theme.radiusSm

            RowLayout {
                anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                spacing: 0

                component HeaderCell: Text {
                    property int cellWidth: 100
                    Layout.preferredWidth: cellWidth
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                    font.letterSpacing: 0.8
                }

                HeaderCell { text: "HEURE UTC"; cellWidth: 90 }
                HeaderCell { text: "SOURCE";    cellWidth: 120 }
                HeaderCell { text: "FRÉQUENCE"; cellWidth: 100 }
                HeaderCell { text: "MODE";      cellWidth: 80 }
                HeaderCell { text: "DURÉE";     cellWidth: 70 }
                HeaderCell { text: "STATUT";    Layout.fillWidth: true }
            }
        }

        // ── Grille de programme ───────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: T.Theme.bgPanel
            radius: T.Theme.radiusMd
            border.color: T.Theme.border
            clip: true

            ListView {
                id: scheduleList
                anchors { fill: parent; margins: 4 }
                model: scheduleModel
                clip: true

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                // Placeholder si vide
                Text {
                    visible: scheduleModel.count === 0
                    anchors.centerIn: parent
                    text: "Aucun programme chargé\nCliquez sur « Actualiser »"
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeSm
                    horizontalAlignment: Text.AlignHCenter
                }

                delegate: Rectangle {
                    width: scheduleList.width
                    height: 32
                    color: index % 2 === 0 ? "transparent" : Qt.rgba(1,1,1,0.03)

                    // Surbrillance survol
                    HoverHandler { id: rowHov }
                    Rectangle {
                        anchors.fill: parent
                        color: "white"
                        opacity: rowHov.hovered ? 0.05 : 0
                        Behavior on opacity { NumberAnimation { duration: 80 } }
                    }

                    RowLayout {
                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                        spacing: 0

                        component Cell: Text {
                            property int cellWidth: 100
                            Layout.preferredWidth: cellWidth
                            color: T.Theme.textMuted
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            elide: Text.ElideRight
                        }

                        Cell { text: model.time      || ""; cellWidth: 90 }
                        Cell { text: model.source     || ""; cellWidth: 120 }
                        Cell { text: model.freq_mhz  ? model.freq_mhz.toFixed(3) + " MHz" : ""; cellWidth: 100 }
                        Cell { text: model.mode       || ""; cellWidth: 80 }
                        Cell { text: model.duration_min ? model.duration_min + " min" : ""; cellWidth: 70 }

                        // Statut coloré
                        Text {
                            Layout.fillWidth: true
                            text: model.status || ""
                            color: {
                                const s = (model.status || "").toLowerCase()
                                if (s.includes("ok") || s.includes("reçu")) return T.Theme.okFg
                                if (s.includes("en cours"))                 return T.Theme.accentLight
                                if (s.includes("manqué") || s.includes("err")) return T.Theme.errFg
                                return T.Theme.textDim
                            }
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // ── Log planificateur ─────────────────────────────────────────
        C.LogView {
            id: planLog
            Layout.fillWidth: true
            height: 100

            Component.onCompleted: {
                // Écouter les messages d'AppBridge
            }
        }
    }

    Connections {
        target: appBridge
        function onJournalLine(text) { planLog.append(text) }
    }
}
