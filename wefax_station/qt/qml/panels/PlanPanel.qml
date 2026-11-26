import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../components" as C
import ".." as T

/*
 * PlanPanel.qml — Onglet PLAN (programme de réceptions DWD/GYA)
 *
 * Recrée le ReceptionPlanMixin Tkinter + horloge UTC
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── Modèle planning ──────────────────────────────────────────────────────
    ListModel { id: scheduleModel }

    // ── État local ───────────────────────────────────────────────────────────
    property string utcTime: Qt.formatTime(new Date(), "HH:mm:ss") + " UTC"
    property string utcDate: Qt.formatDate(new Date(), "dddd dd MMM yyyy")
    property string filterStation: "TOUTES"
    property string filterMode:    "TOUS"

    // Mise à jour horloge chaque seconde
    Timer {
        interval: 1000; running: true; repeat: true
        onTriggered: {
            root.utcTime = Qt.formatDateTime(new Date(), "HH:mm:ss") + " UTC"
            root.utcDate = Qt.formatDateTime(new Date(), "dddd dd MMM yyyy")
        }
    }

    // ── Connexion aux ponts ──────────────────────────────────────────────────
    Connections {
        target: appBridge

        function onScheduleChanged(schedule) {
            scheduleModel.clear()
            for (let i = 0; i < schedule.length; i++) {
                scheduleModel.append(schedule[i])
            }
        }
    }

    // ── Remplissage initial depuis schedules.py (via bridge) ─────────────────
    Component.onCompleted: {
        appBridge.requestScheduleRefresh()
    }

    // ── Mise en page principale ──────────────────────────────────────────────
    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacing

        // ── Horloge UTC + filtres ─────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: T.Theme.spacing

            // Horloge
            Rectangle {
                width: 220; height: 56
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                Column {
                    anchors.centerIn: parent
                    spacing: 2

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.utcTime
                        color: T.Theme.textPrimary
                        font.family: T.Theme.fontMono
                        font.pixelSize: 22
                        font.bold: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.utcDate
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                    }
                }
            }

            // Filtre station
            Text { text: "Station :"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
            C.DropDown {
                model: ["TOUTES", "DWD (DDH3/DDK3/DDK6)", "Northwood (GYA)", "RTTY"]
                currentText: root.filterStation
                onSelected: (txt) => root.filterStation = txt
            }

            // Filtre mode
            Text { text: "Mode :"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
            C.DropDown {
                model: ["TOUS", "WEFAX", "RTTY", "NAVTEX"]
                currentText: root.filterMode
                onSelected: (txt) => root.filterMode = txt
            }

            Item { Layout.fillWidth: true }

            C.FlatButton {
                text:    "🔄 Rafraîchir"
                accent:  false
                onClicked: appBridge.requestScheduleRefresh()
            }
            C.FlatButton {
                text:    "▶ Prochaine"
                accent:  true
                onClicked: appBridge.startNextScheduled()
            }
        }

        // ── En-têtes colonnes ─────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 24
            color: T.Theme.bgSurface
            radius: T.Theme.radiusSm

            RowLayout {
                anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                spacing: 0

                component Hdr: Text {
                    property int cw: 80
                    Layout.preferredWidth: cw
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                    font.letterSpacing: 1
                }
                Hdr { text: "HEURE UTC"; cw: 90 }
                Hdr { text: "DURÉE";     cw: 55 }
                Hdr { text: "ÉMETTEUR";  cw: 160; Layout.fillWidth: true }
                Hdr { text: "FRÉQUENCE"; cw: 90 }
                Hdr { text: "MODE";      cw: 70 }
                Hdr { text: "STATUT";    cw: 80 }
                Hdr { text: "";          cw: 70 }
            }
        }

        // ── Liste planning ────────────────────────────────────────────────
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: scheduleModel
            clip:  true
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            // Filtre dynamique — liste proxy simulée via visible
            delegate: Rectangle {
                readonly property bool matchStation: root.filterStation === "TOUTES"
                    || (root.filterStation.indexOf("DWD") >= 0 && (model.station_id || "").indexOf("DDH") >= 0)
                    || (root.filterStation.indexOf("DWD") >= 0 && (model.station_id || "").indexOf("DDK") >= 0)
                    || (root.filterStation.indexOf("GYA") >= 0 && (model.station_id || "").indexOf("GYA") >= 0)
                    || (root.filterStation.indexOf("RTTY") >= 0 && (model.mode || "") === "RTTY")

                readonly property bool matchMode: root.filterMode === "TOUS"
                    || model.mode === root.filterMode

                visible:  matchStation && matchMode
                height:   matchStation && matchMode ? 30 : 0
                width:    ListView.view.width

                readonly property bool isNext:   model.status === "PROCHAIN"
                readonly property bool isActive: model.status === "EN COURS"

                color: isActive ? Qt.rgba(0.14, 0.38, 0.92, 0.12) :
                       isNext   ? Qt.rgba(1, 0.65, 0,    0.08) :
                       index % 2 === 0 ? "transparent" : Qt.rgba(1,1,1,0.03)

                // Bordure gauche colorée
                Rectangle {
                    width: 3; height: parent.height
                    color: parent.isActive ? T.Theme.accent :
                           parent.isNext   ? T.Theme.warnFg : "transparent"
                }

                RowLayout {
                    anchors { fill: parent; leftMargin: 11; rightMargin: 8 }
                    spacing: 0

                    component Cell: Text {
                        property int cw: 80
                        Layout.preferredWidth: cw
                        color: T.Theme.textMuted
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeSm
                        elide: Text.ElideRight
                    }

                    Cell {
                        text:  model.time_utc || "---"
                        cw:    90
                        color: parent.parent.parent.isNext ? T.Theme.warnFg : T.Theme.textPrimary
                        font.bold: parent.parent.parent.isNext
                    }
                    Cell { text: model.duration_min !== undefined ? model.duration_min + "'" : "---"; cw: 55 }
                    Cell { text: model.station_name || "---"; Layout.fillWidth: true }
                    Cell { text: (model.freq_khz !== undefined ? model.freq_khz.toFixed(1) : "---") + " kHz"; cw: 90 }

                    // Badge mode
                    Rectangle {
                        Layout.preferredWidth: 60
                        height: 18
                        radius: T.Theme.radiusSm
                        color: T.Theme.modeColor(model.mode || "")
                        opacity: 0.3

                        Text {
                            anchors.centerIn: parent
                            text: model.mode || "---"
                            color: T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                            font.bold: true
                        }
                    }

                    // Statut
                    Cell {
                        text: model.status || "---"
                        cw: 80
                        color: parent.parent.parent.isActive ? T.Theme.okFg :
                               parent.parent.parent.isNext   ? T.Theme.warnFg : T.Theme.textDim
                    }

                    // Bouton Lancer
                    C.FlatButton {
                        text:    "Lancer"
                        accent:  parent.parent.parent.isNext
                        enabled: model.status !== "PASSÉ"
                        implicitWidth:  60
                        implicitHeight: 20
                        Layout.preferredWidth: 60
                        onClicked: {
                            appBridge.launchScheduledReception(model.station_id, model.freq_khz)
                        }
                    }
                }

                HoverHandler { id: rowHov }
                Rectangle {
                    anchors.fill: parent; color: "white"
                    opacity: rowHov.hovered ? 0.03 : 0
                }
            }

            // Placeholder si vide
            Text {
                anchors.centerIn: parent
                visible: scheduleModel.count === 0
                text: "Programme chargement…\n\nLes émissions DWD (Pinneberg) et\nNorthwood (GYA) apparaîtront ici\navec leurs horaires UTC."
                color: T.Theme.textDim
                font.family: T.Theme.fontMono
                font.pixelSize: T.Theme.fontSizeSm
                horizontalAlignment: Text.AlignHCenter
            }
        }

        // ── Prochaine réception + actions rapides ─────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 50
            color: T.Theme.bgPanel
            radius: T.Theme.radiusMd
            border.color: T.Theme.border

            RowLayout {
                anchors { fill: parent; margins: T.Theme.spacing }
                spacing: T.Theme.spacing

                Text {
                    id: nextLabel
                    text: "PROCHAINE ÉMISSION :"
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                    font.letterSpacing: 1
                }

                Text {
                    text: {
                        for (let i = 0; i < scheduleModel.count; i++) {
                            const e = scheduleModel.get(i)
                            if (e.status === "PROCHAIN") return e.time_utc + " — " + e.station_name + " (" + e.freq_khz + " kHz)"
                        }
                        return "Aucune dans les prochaines heures"
                    }
                    color: T.Theme.warnFg
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeSm
                    font.bold: true
                }

                Item { Layout.fillWidth: true }

                C.FlatButton {
                    text:    "📥 Télécharger cartes web"
                    accent:  false
                    onClicked: appBridge.downloadWebCharts()
                }
            }
        }
    }
}
