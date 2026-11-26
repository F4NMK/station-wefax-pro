import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QC
import "../components" as C
import ".." as T

/*
 * MeteoPanel.qml — Onglet MÉTÉO (synoptique + bulletins)
 *
 * Recrée le WeatherDeskMixin Tkinter + BulletinDeskMixin
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── État local ───────────────────────────────────────────────────────────
    property var weatherData: ({
        wind_speed:   null,
        beaufort:     null,
        temp:         null,
        pressure:     null,
        humidity:     null,
        cloud_cover:  null,
        wx_desc:      "---",
        source:       "---",
        updated_at:   "---"
    })
    property var bulletins:   []
    property int activeTab:   0     // 0=Synoptique, 1=Bulletins, 2=Cartes

    // ── Connexion aux ponts ──────────────────────────────────────────────────
    Connections {
        target: appBridge
        function onWeatherUpdated(data) {
            root.weatherData = data
        }
        function onBulletinsUpdated(list) {
            root.bulletins = list
        }
    }

    // ── Mise en page principale ──────────────────────────────────────────────
    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacing

        // ── Navigation interne ────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: T.Theme.spacing

            Repeater {
                model: ["🌬 Synoptique", "📰 Bulletins", "🗺 Cartes GRIB"]
                delegate: C.FlatButton {
                    text:   modelData
                    accent: root.activeTab === index
                    Layout.fillWidth: true
                    onClicked: root.activeTab = index
                }
            }

            Item { Layout.fillWidth: true }

            C.FlatButton {
                text:    "🔄 Actualiser"
                accent:  false
                onClicked: appBridge.refreshWeather()
            }
        }

        // ── Onglets ───────────────────────────────────────────────────────
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.activeTab

            // ── 0 : SYNOPTIQUE ────────────────────────────────────────────
            Item {
                ColumnLayout {
                    anchors { fill: parent }
                    spacing: T.Theme.spacing

                    // Source + horodatage
                    Rectangle {
                        Layout.fillWidth: true
                        height: 36
                        color: T.Theme.bgPanel
                        radius: T.Theme.radiusMd
                        border.color: T.Theme.border

                        RowLayout {
                            anchors { fill: parent; margins: T.Theme.spacing }
                            Text {
                                text: "Source : " + root.weatherData.source
                                color: T.Theme.textDim
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeSm
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "Mise à jour : " + root.weatherData.updated_at
                                color: T.Theme.textDim
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeSm
                            }
                        }
                    }

                    // Tuiles météo 3×2
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 3
                        rowSpacing: T.Theme.spacing
                        columnSpacing: T.Theme.spacing

                        component MeteoTile: Rectangle {
                            property string icon:  "?"
                            property string label: "---"
                            property string value: "---"
                            property string unit:  ""
                            property string trend: ""  // "↑" "↓" "→"
                            property bool   alert: false

                            Layout.fillWidth: true
                            height: 100
                            color: T.Theme.bgPanel
                            radius: T.Theme.radiusMd
                            border.color: alert ? T.Theme.warnFg : T.Theme.border

                            Column {
                                anchors.centerIn: parent
                                spacing: 4

                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: icon
                                    font.pixelSize: 24
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: label
                                    color: T.Theme.textDim
                                    font.family: T.Theme.fontMono
                                    font.pixelSize: T.Theme.fontSizeXs
                                    font.letterSpacing: 1
                                }
                                Row {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    spacing: 4

                                    Text {
                                        text: value
                                        color: alert ? T.Theme.warnFg : T.Theme.textPrimary
                                        font.family: T.Theme.fontMono
                                        font.pixelSize: T.Theme.fontSizeLg
                                        font.bold: true
                                    }
                                    Text {
                                        text: unit
                                        color: T.Theme.textDim
                                        font.family: T.Theme.fontMono
                                        font.pixelSize: T.Theme.fontSizeSm
                                        anchors.bottom: parent.bottom
                                        anchors.bottomMargin: 2
                                    }
                                    Text {
                                        text: trend
                                        color: trend === "↑" ? T.Theme.errFg : (trend === "↓" ? T.Theme.okFg : T.Theme.textDim)
                                        font.family: T.Theme.fontMono
                                        font.pixelSize: T.Theme.fontSizeSm
                                        anchors.bottom: parent.bottom
                                        anchors.bottomMargin: 2
                                    }
                                }
                            }
                        }

                        MeteoTile {
                            icon:  "💨"
                            label: "VENT"
                            value: root.weatherData.wind_speed !== null ? root.weatherData.wind_speed.toFixed(1) : "---"
                            unit:  root.weatherData.wind_speed !== null ? " kt" : ""
                            alert: root.weatherData.wind_speed !== null && root.weatherData.wind_speed > 20
                        }
                        MeteoTile {
                            icon:  "🌊"
                            label: "BEAUFORT"
                            value: root.weatherData.beaufort !== null ? String(root.weatherData.beaufort) : "---"
                            unit:  ""
                            alert: root.weatherData.beaufort !== null && root.weatherData.beaufort >= 7
                        }
                        MeteoTile {
                            icon:  "🌡"
                            label: "TEMPÉRATURE"
                            value: root.weatherData.temp !== null ? root.weatherData.temp.toFixed(1) : "---"
                            unit:  "°C"
                        }
                        MeteoTile {
                            icon:  "🔵"
                            label: "PRESSION"
                            value: root.weatherData.pressure !== null ? root.weatherData.pressure.toFixed(0) : "---"
                            unit:  "hPa"
                        }
                        MeteoTile {
                            icon:  "💧"
                            label: "HUMIDITÉ"
                            value: root.weatherData.humidity !== null ? root.weatherData.humidity.toFixed(0) : "---"
                            unit:  "%"
                        }
                        MeteoTile {
                            icon:  "☁"
                            label: "COUVERTURE"
                            value: root.weatherData.cloud_cover !== null ? root.weatherData.cloud_cover.toFixed(0) : "---"
                            unit:  "%"
                        }
                    }

                    // Description générale
                    Rectangle {
                        Layout.fillWidth: true
                        height: 50
                        color: T.Theme.bgPanel
                        radius: T.Theme.radiusMd
                        border.color: T.Theme.border

                        Text {
                            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                            text: root.weatherData.wx_desc
                            color: T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            wrapMode: Text.WrapAnywhere
                        }
                    }

                    Item { Layout.fillHeight: true }
                }
            }

            // ── 1 : BULLETINS ─────────────────────────────────────────────
            Item {
                ColumnLayout {
                    anchors { fill: parent }
                    spacing: T.Theme.spacing

                    // En-têtes colonnes
                    Rectangle {
                        Layout.fillWidth: true
                        height: 24
                        color: T.Theme.bgSurface
                        radius: T.Theme.radiusSm

                        RowLayout {
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            spacing: 0

                            component BHdr: Text {
                                property int cw: 100
                                Layout.preferredWidth: cw
                                color: T.Theme.textDim
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeXs
                                font.letterSpacing: 1
                            }
                            BHdr { text: "DATE/HEURE"; cw: 110 }
                            BHdr { text: "TYPE";       cw: 80 }
                            BHdr { text: "STATION";    cw: 90 }
                            BHdr { text: "RÉSUMÉ";     Layout.fillWidth: true }
                        }
                    }

                    // Liste bulletins
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: root.bulletins
                        clip: true
                        QC.ScrollBar.vertical: QC.ScrollBar { policy: QC.ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 28
                            color: index % 2 === 0 ? "transparent" : Qt.rgba(1,1,1,0.03)

                            HoverHandler { id: bHov }
                            Rectangle {
                                anchors.fill: parent; color: "white"
                                opacity: bHov.hovered ? 0.05 : 0
                            }

                            RowLayout {
                                anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                spacing: 0

                                component BCell: Text {
                                    property int cw: 100
                                    Layout.preferredWidth: cw
                                    color: T.Theme.textMuted
                                    font.family: T.Theme.fontMono
                                    font.pixelSize: T.Theme.fontSizeSm
                                    elide: Text.ElideRight
                                }

                                BCell { text: modelData.dt || "---";      cw: 110 }
                                BCell { text: modelData.btype || "---";   cw: 80;  color: T.Theme.accentLight }
                                BCell { text: modelData.station || "---"; cw: 90 }
                                BCell { text: modelData.summary || "---"; Layout.fillWidth: true }
                            }

                            TapHandler { onDoubleTapped: appBridge.openBulletin(modelData.id) }
                        }

                        // Placeholder
                        Text {
                            anchors.centerIn: parent
                            visible: root.bulletins.length === 0
                            text: "Aucun bulletin reçu\n\nActivez la réception pour\ncollectes les bulletins RTTY / NAVTEX."
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }
            }

            // ── 2 : CARTES GRIB ──────────────────────────────────────────
            Item {
                Text {
                    anchors.centerIn: parent
                    text: "🗺\n\nCartes GRIB / Prévisions\n\nFonction en cours de développement.\nLes données GRIB seront\naccessibles ici."
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeSm
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
