import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "." as T

/*
 * WeatherDeskPanel.qml — Poste météo analyse assistée
 *
 * Fonctionnalités portées depuis WeatherDeskMixin (Tkinter 2.14) :
 *   - Calcul géostrophique (gradient / vent théorique)
 *   - Cartes Internet DWD (téléchargement et affichage)
 *   - Observations locales (pression, tendance, vent, ciel, T°)
 *   - Bulletin météo textuel compilé
 *   - Avertissements physiques intégrés
 */
Rectangle {
    id: root
    color: "#0d1b2a"

    // ── États ────────────────────────────────────────────────────────────────
    property string calcReport:    ""
    property bool   calcRunning:   false
    property string webChartPath:  ""
    property string webChartLabel: ""
    property bool   chartLoading:  false
    property var    webChartKeys:  []

    // ── Connexions AppBridge ─────────────────────────────────────────────────
    Connections {
        target: appBridge

        function onWeatherCalcResult(report) {
            root.calcReport  = report
            root.calcRunning = false
            calcOutput.text  = report
        }

        function onWebChartReady(path, label) {
            root.webChartPath  = path
            root.webChartLabel = label
            root.chartLoading  = false
            webChart.source    = "file:///" + path.replace(/\\/g, "/") + "?" + Date.now()
        }

        function onStatusChanged(text) {
            if (root.chartLoading && text.startsWith("⚠️"))
                root.chartLoading = false
        }
    }

    // ── Initialisation ───────────────────────────────────────────────────────
    Component.onCompleted: {
        root.webChartKeys = appBridge.listWebCharts()
        for (var i = 0; i < root.webChartKeys.length; i++) {
            webChartCombo.model.append({ text: root.webChartKeys[i] })
        }
    }

    // ── Layout principal : onglets ───────────────────────────────────────────
    ColumnLayout {
        anchors.fill:    parent
        anchors.margins: 8
        spacing:         6

        // Barre d'onglets internes
        Row {
            spacing: 2

            Repeater {
                model: ["🌬 Calcul géostrophique", "🌐 Cartes Web DWD", "🌡 Observations locales"]

                Rectangle {
                    width:  implicitWidth + 24
                    height: 30
                    radius: 4
                    color:  innerTabs.currentIndex === index
                            ? "#1e3a5f"
                            : (tabMa.containsMouse ? "#152638" : "#0a1520")
                    border.color: innerTabs.currentIndex === index ? "#3a80c0" : "#1e3a5f"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text:  modelData
                        color: innerTabs.currentIndex === index ? "#7ec8e3" : "#607890"
                        font.pixelSize: 11
                    }
                    MouseArea {
                        id: tabMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape:  Qt.PointingHandCursor
                        onClicked:    innerTabs.currentIndex = index
                    }
                }
            }
        }

        // Contenu onglets
        StackLayout {
            id:                innerTabs
            Layout.fillWidth:  true
            Layout.fillHeight: true

            // ── Onglet 1 : Calcul géostrophique ──────────────────────────
            RowLayout {
                spacing: 8

                // Formulaire de saisie
                Rectangle {
                    Layout.preferredWidth: 350
                    Layout.fillHeight:     true
                    color:                 "#0a1520"
                    radius:                6
                    border.color:          "#1e3a5f"
                    border.width:          1

                    ColumnLayout {
                        anchors {
                            fill: parent
                            margins: 12
                        }
                        spacing: 8

                        Text {
                            text:  "🌬 Calcul physique assisté"
                            color: "#b0c2d4"
                            font { pixelSize: 13; bold: true }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Calcul automatique après validation des mesures.\n"
                                + "Ce module ne reconnaît pas les isobares, fronts ou cartouches de façon fiable."
                            color:    "#c05020"
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }

                        // Champ : validité
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Validité UTC (AAAA-MM-JJ HH:MM)"; color: "#7a9aba"; font.pixelSize: 10 }
                            TextField {
                                id: validField
                                width: parent.width
                                placeholderText: "2026-11-27 12:00"
                                color: "#b0c2d4"
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            }
                        }

                        // Champ : type
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Type : analyse ou prévision"; color: "#7a9aba"; font.pixelSize: 10 }
                            ComboBox {
                                id: typeCombo
                                width: parent.width
                                model: ["analyse", "prévision"]
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                                contentItem: Text { text: typeCombo.displayText; color: "#b0c2d4"; font.pixelSize: 11; leftPadding: 6 }
                            }
                        }

                        // Champ : latitude
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Latitude du secteur, degrés (+ au nord)"; color: "#7a9aba"; font.pixelSize: 10 }
                            TextField {
                                id: latField
                                width: parent.width
                                placeholderText: "43.5"
                                color: "#b0c2d4"
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            }
                        }

                        // Champ : écart isobares
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Écart entre les deux isobares (hPa)"; color: "#7a9aba"; font.pixelSize: 10 }
                            TextField {
                                id: dpField
                                width: parent.width
                                placeholderText: "4"
                                color: "#b0c2d4"
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            }
                        }

                        // Champ : distance
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Distance perpendiculaire réelle (km)"; color: "#7a9aba"; font.pixelSize: 10 }
                            TextField {
                                id: distField
                                width: parent.width
                                placeholderText: "250"
                                color: "#b0c2d4"
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            }
                        }

                        // Champ : azimut basses pressions
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Azimut vrai VERS les basses pressions (facultatif)"; color: "#7a9aba"; font.pixelSize: 10 }
                            TextField {
                                id: lowField
                                width: parent.width
                                placeholderText: ""
                                color: "#b0c2d4"
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            }
                        }

                        // Champ : front
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Front proche confirmé"; color: "#7a9aba"; font.pixelSize: 10 }
                            ComboBox {
                                id: frontCombo
                                width: parent.width
                                model: ["non déterminé", "froid", "chaud", "occlus"]
                                font.pixelSize: 11
                                background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                                contentItem: Text { text: frontCombo.displayText; color: "#b0c2d4"; font.pixelSize: 11; leftPadding: 6 }
                            }
                        }

                        // Case à cocher confirmation
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            CheckBox {
                                id: confirmedCheck
                                text: ""
                                checked: false
                                indicator: Rectangle {
                                    implicitWidth: 16; implicitHeight: 16
                                    radius: 2
                                    color:        confirmedCheck.checked ? "#2a6a8a" : "#152638"
                                    border.color: confirmedCheck.checked ? "#3a90ba" : "#2a5080"
                                    border.width: 1
                                    Text {
                                        anchors.centerIn: parent
                                        visible: confirmedCheck.checked
                                        text:  "✓"; color: "#7ec8e3"; font.pixelSize: 10
                                    }
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text:     "Je confirme le secteur, l'échelle, la validité et les isobares mesurées"
                                color:    "#b0c2d4"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                        }

                        // Bouton Calculer
                        Rectangle {
                            Layout.fillWidth: true
                            height:  34
                            radius:  5
                            color:   calcBtn.containsMouse && confirmedCheck.checked
                                     ? "#1a5a2a" : (confirmedCheck.checked ? "#0f3a1a" : "#0a1a0a")
                            border.color: confirmedCheck.checked ? "#2a8a3a" : "#1e3a2a"
                            border.width: 1
                            opacity: confirmedCheck.checked ? 1.0 : 0.5

                            Text {
                                anchors.centerIn: parent
                                text:  root.calcRunning ? "Calcul en cours…" : "Calculer"
                                color: confirmedCheck.checked ? "#70d080" : "#3a6a4a"
                                font { pixelSize: 12; bold: true }
                            }
                            MouseArea {
                                id: calcBtn
                                anchors.fill: parent
                                hoverEnabled: true
                                enabled:      confirmedCheck.checked && !root.calcRunning
                                cursorShape:  confirmedCheck.checked ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    root.calcRunning = true
                                    var params = JSON.stringify({
                                        dp:    parseFloat(dpField.text.replace(",", ".")),
                                        dist:  parseFloat(distField.text.replace(",", ".")),
                                        lat:   parseFloat(latField.text.replace(",", ".")),
                                        low:   lowField.text.trim() ? parseFloat(lowField.text.replace(",", ".")) : null,
                                        front: frontCombo.currentText,
                                        type:  typeCombo.currentText,
                                        valid: validField.text.trim()
                                    })
                                    appBridge.computeGeostrophic(params)
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                // Résultat du calcul
                Rectangle {
                    Layout.fillWidth:  true
                    Layout.fillHeight: true
                    color:             "#0a1520"
                    radius:            6
                    border.color:      "#1e3a5f"
                    border.width:      1

                    ColumnLayout {
                        anchors { fill: parent; margins: 10 }
                        spacing: 6

                        Text {
                            text:  "📋 Rapport géostrophique"
                            color: "#b0c2d4"
                            font { pixelSize: 12; bold: true }
                        }

                        ScrollView {
                            Layout.fillWidth:  true
                            Layout.fillHeight: true
                            clip:              true

                            TextArea {
                                id:         calcOutput
                                text:       "En attente de mesures confirmées.\nL'espacement en pixels seul n'est pas une distance géographique."
                                color:      "#c0d8f0"
                                font.pixelSize: 11
                                font.family:    "Courier New, monospace"
                                wrapMode:   TextArea.Wrap
                                readOnly:   true
                                background: Rectangle { color: "transparent" }
                            }
                        }

                        // Bouton copier
                        Rectangle {
                            width:  120; height: 28
                            radius: 4
                            visible: root.calcReport.length > 0
                            color:   copyMa.containsMouse ? "#1e3a5f" : "#152638"
                            border.color: "#2a5080"; border.width: 1
                            Text { anchors.centerIn: parent; text: "📋 Copier"; color: "#7ec8e3"; font.pixelSize: 10 }
                            MouseArea {
                                id: copyMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape:  Qt.PointingHandCursor
                                onClicked:    calcOutput.selectAll(); calcOutput.copy()
                            }
                        }
                    }
                }
            }

            // ── Onglet 2 : Cartes Web DWD ────────────────────────────────
            ColumnLayout {
                spacing: 6

                // Sélecteur + bouton
                RowLayout {
                    Layout.fillWidth: true
                    spacing:          6

                    Text {
                        text:  "🌐 Carte DWD :"
                        color: "#b0c2d4"
                        font.pixelSize: 11
                    }

                    ComboBox {
                        id:              webChartCombo
                        Layout.fillWidth: true
                        model:           ListModel { }
                        font.pixelSize:  10
                        background: Rectangle {
                            color:        "#152638"
                            radius:       3
                            border.color: "#2a5080"
                            border.width: 1
                        }
                        contentItem: Text {
                            text:          webChartCombo.displayText
                            color:         "#b0c2d4"
                            font.pixelSize: 10
                            leftPadding:   6
                            elide:         Text.ElideRight
                        }
                    }

                    Rectangle {
                        width:  120; height: 30
                        radius: 4
                        color:  dlMa.containsMouse ? "#1a4a6a" : "#0f2a4a"
                        border.color: "#2a7aaa"; border.width: 1
                        opacity: root.chartLoading ? 0.6 : 1.0

                        Text {
                            anchors.centerIn: parent
                            text:  root.chartLoading ? "⏳ Chargement…" : "⬇️ Télécharger"
                            color: "#70c0e8"
                            font.pixelSize: 10
                        }
                        MouseArea {
                            id: dlMa
                            anchors.fill: parent
                            hoverEnabled: true
                            enabled:      !root.chartLoading && webChartCombo.currentIndex >= 0
                            cursorShape:  Qt.PointingHandCursor
                            onClicked: {
                                root.chartLoading  = true
                                root.webChartPath  = ""
                                webChart.source    = ""
                                appBridge.downloadWebChart(webChartCombo.currentText)
                            }
                        }
                    }
                }

                // Label carte chargée
                Text {
                    visible:        root.webChartLabel.length > 0
                    text:           "✅ " + root.webChartLabel
                    color:          "#50c080"
                    font.pixelSize: 10
                }

                // Viewer carte web
                Rectangle {
                    Layout.fillWidth:  true
                    Layout.fillHeight: true
                    color:             "#050e18"
                    radius:            6
                    border.color:      "#1e3a5f"
                    border.width:      1
                    clip:              true

                    Text {
                        anchors.centerIn: parent
                        visible:          root.webChartPath.length === 0 && !root.chartLoading
                        text:             "Sélectionner et télécharger\nune carte DWD"
                        color:            "#2a4a6a"
                        font.pixelSize:   15
                        horizontalAlignment: Text.AlignHCenter
                    }

                    BusyIndicator {
                        anchors.centerIn: parent
                        running:          root.chartLoading
                    }

                    Image {
                        id:           webChart
                        anchors.fill: parent
                        anchors.margins: 4
                        fillMode:     Image.PreserveAspectFit
                        visible:      root.webChartPath.length > 0
                        asynchronous: true
                        cache:        false
                    }

                    // Dimensions
                    Text {
                        anchors { bottom: parent.bottom; right: parent.right; margins: 6 }
                        visible:         webChart.status === Image.Ready
                        text:            webChart.sourceSize.width + "×" + webChart.sourceSize.height + " px"
                        color:           "#3a6a9a"
                        font.pixelSize:  10
                    }
                }

                Text {
                    text:  "⚠️ Consultation uniquement — pas une réception radio IC-705"
                    color: "#c08030"
                    font.pixelSize: 10
                }
            }

            // ── Onglet 3 : Observations locales ──────────────────────────
            ColumnLayout {
                spacing: 8

                Text {
                    text:  "🌡 Observations locales (station QTH)"
                    color: "#b0c2d4"
                    font { pixelSize: 13; bold: true }
                }

                // Grille d'observations
                GridLayout {
                    columns:          2
                    columnSpacing:    12
                    rowSpacing:       8
                    Layout.fillWidth: true

                    Repeater {
                        model: [
                            { label: "Date/heure UTC",   placeholder: "2026-11-27 12:00", id: "time"   },
                            { label: "Pression hPa",     placeholder: "1015",             id: "press"  },
                            { label: "Température °C",   placeholder: "18",               id: "temp"   },
                            { label: "Humidité %",       placeholder: "65",               id: "rh"     },
                        ]

                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: modelData.label; color: "#7a9aba"; font.pixelSize: 10 }
                            TextField {
                                width: parent.width
                                placeholderText: modelData.placeholder
                                color: "#b0c2d4"
                                font.pixelSize: 11
                                background: Rectangle {
                                    color:        "#152638"; radius: 3
                                    border.color: "#2a5080"; border.width: 1
                                }
                            }
                        }
                    }

                    // Tendance pression
                    Column {
                        Layout.fillWidth: true
                        spacing: 3
                        Text { text: "Tendance 3 h"; color: "#7a9aba"; font.pixelSize: 10 }
                        ComboBox {
                            width: parent.width
                            model: ["non renseigné", "hausse rapide (>3 hPa)", "hausse lente (1-3 hPa)",
                                    "stable (±1 hPa)", "baisse lente (1-3 hPa)", "baisse rapide (>3 hPa)"]
                            font.pixelSize: 10
                            background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            contentItem: Text { text: parent.displayText; color: "#b0c2d4"; font.pixelSize: 10; leftPadding: 6; elide: Text.ElideRight }
                        }
                    }

                    // Vent
                    Column {
                        Layout.fillWidth: true
                        spacing: 3
                        Text { text: "Vent (direction, force)"; color: "#7a9aba"; font.pixelSize: 10 }
                        ComboBox {
                            width: parent.width
                            model: ["non renseigné", "calme", "N faible", "NE faible", "E faible",
                                    "SE faible", "S faible", "SO faible", "O faible", "NO faible",
                                    "N modéré", "NE modéré", "SO modéré", "O fort", "SO fort"]
                            font.pixelSize: 10
                            background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            contentItem: Text { text: parent.displayText; color: "#b0c2d4"; font.pixelSize: 10; leftPadding: 6; elide: Text.ElideRight }
                        }
                    }

                    // Ciel
                    Column {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        spacing: 3
                        Text { text: "Couverture nuageuse"; color: "#7a9aba"; font.pixelSize: 10 }
                        ComboBox {
                            width: parent.width
                            model: ["non renseigné", "dégagé (0-1/8)", "peu nuageux (2-3/8)",
                                    "nuageux (4-5/8)", "très nuageux (6-7/8)", "couvert (8/8)",
                                    "brouillard", "pluie", "averse", "orage"]
                            font.pixelSize: 10
                            background: Rectangle { color: "#152638"; radius: 3; border.color: "#2a5080"; border.width: 1 }
                            contentItem: Text { text: parent.displayText; color: "#b0c2d4"; font.pixelSize: 10; leftPadding: 6; elide: Text.ElideRight }
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text:     "ℹ️ Ces observations locales complètent l'analyse WEFAX.\n"
                            + "Pour compiler un bulletin complet, utilisez le Panneau Météo principal (onglet 🌦 MÉTÉO)."
                    color:    "#5a7a9a"
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
