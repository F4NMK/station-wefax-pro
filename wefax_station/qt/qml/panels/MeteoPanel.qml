import QtQuick
import QtQuick.Layouts
import ".." as T

/*
 * MeteoPanel.qml — Onglet MÉTÉO
 *
 * Affiche les dernières données GRIB / nowcast reçues.
 * Context property attendu : appBridge (AppBridge)
 *
 * Les données météo sont en lecture seule dans ce panneau ;
 * le moteur GRIB/nowcast reste dans Python.
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // Données météo passées par AppBridge via scheduleChanged
    property var meteoData: null

    Connections {
        target: appBridge
        function onScheduleChanged() {
            // TODO : AppBridge devra exposer un slot getMeteoSummary()
            // et un signal meteoUpdated(var data) — à implémenter en passe 2
        }
    }

    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ── En-tête ────────────────────────────────────────────────────
        Text {
            text: "DONNÉES MÉTÉO"
            color: T.Theme.textDim
            font.family: T.Theme.fontMono
            font.pixelSize: T.Theme.fontSizeXs
            font.letterSpacing: 2
        }

        // ── Grille de tuiles météo ─────────────────────────────────────
        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: T.Theme.spacing
            rowSpacing:    T.Theme.spacing

            // Tuile générique
            component MeteoTile: Rectangle {
                property string label: ""
                property string value: "---"
                property string unit:  ""
                property color  valueColor: T.Theme.textPrimary

                Layout.fillWidth: true
                height: 80
                color:  T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                Column {
                    anchors.centerIn: parent
                    spacing: 4

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: label
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                        font.letterSpacing: 1
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: value + (unit !== "" ? " " + unit : "")
                        color: valueColor
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeLg
                        font.bold: true
                    }
                }
            }

            MeteoTile { label: "VENT MOY."    ; value: meteoData ? meteoData.wind_ms.toFixed(1)  : "---"; unit: "m/s" }
            MeteoTile { label: "BEAUFORT"      ; value: meteoData ? String(meteoData.beaufort)     : "---"; unit: "Bf" }
            MeteoTile { label: "TEMPÉRATURE"   ; value: meteoData ? meteoData.temp_c.toFixed(1)   : "---"; unit: "°C" }
            MeteoTile { label: "PRESSION"      ; value: meteoData ? meteoData.pressure.toFixed(0) : "---"; unit: "hPa" }
            MeteoTile { label: "HUMIDITÉ"      ; value: meteoData ? meteoData.humidity.toFixed(0) : "---"; unit: "%" }
            MeteoTile { label: "COUVERTURE NU."; value: meteoData ? meteoData.cloud_cover.toFixed(0) : "---"; unit: "%" }
        }

        // ── Placeholder carte / zone ───────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color:  T.Theme.bgCanvas
            radius: T.Theme.radiusMd
            border.color: T.Theme.border

            Text {
                anchors.centerIn: parent
                text: "Carte GRIB / prévision — à implémenter\n(rendu canvas Python → QML)"
                color: T.Theme.textDim
                font.family: T.Theme.fontMono
                font.pixelSize: T.Theme.fontSizeSm
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
