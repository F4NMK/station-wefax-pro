import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

/*
 * BulletinDeskPanel.qml — Poste Météo & Bulletin (port de BulletinDeskMixin 2.14)
 *
 * 3 sous-onglets :
 *   1 · Réceptions 24 h — liste des cartes et bulletins reçus, sélection
 *   2 · Bulletin        — compilation et édition du bulletin opérateur
 *   3 · Statistiques    — tableau de réception par station
 */
Rectangle {
    id: root
    color: "#0d1b2a"

    // ── État ─────────────────────────────────────────────────────────────────
    property var    allDocs:       []          // liste brute chargée depuis le pont
    property var    includedIds:   ({})        // { id: true } sélectionnés
    property string zone:          ""          // zone d'analyse opérateur
    property bool   loadingDocs:   false
    property bool   compiling:     false
    property string bulletinText:  ""
    property string statsText:     ""
    property bool   savedVisible:  false

    // ── Connexions pont ───────────────────────────────────────────────────────
    Connections {
        target: appBridge

        function onBulletinTextReady(text) {
            root.compiling    = false
            root.bulletinText = text
            bulletinEdit.text = text
        }

        function onBulletinStatsReady(text) {
            root.statsText = text
            statsView.text = text
        }

        function onBulletinSaved(path) {
            root.savedVisible = true
            savedTimer.restart()
        }
    }

    // ── Initialisaton ─────────────────────────────────────────────────────────
    Component.onCompleted: root.refreshDocs()

    function refreshDocs() {
        root.loadingDocs = true
        root.includedIds = {}
        // getBulletinDocs retourne la liste directement (slot synchrone QVariantList)
        var docs = appBridge.getBulletinDocs(24)
        // Traitement inline (pas de signal — slot synchrone)
        root.loadingDocs = false
        root.allDocs     = docs
        docsModel.clear()
        for (var i = 0; i < docs.length; i++) {
            var d = docs[i]
            docsModel.append({
                "docId":        d.id      || "",
                "kind":         d.kind    || "",
                "start_utc":    d.start_utc || "",
                "station":      d.station || "",
                "freq_khz":     d.freq_khz != null ? Number(d.freq_khz).toFixed(1) : "",
                "status":       d.status  || "",
                "reliability":  d.reliability_pct != null
                                  ? d.reliability_pct + " % " + (d.reliability_grade || "")
                                  : "—",
                "product":      d.product || "",
                "included":     false,
            })
        }
        // Sélection par défaut : bulletins texte + 1re carte par station
        var seen = {}
        var newIncluded = {}
        for (var j = 0; j < docsModel.count; j++) {
            var item = docsModel.get(j)
            var iid  = item.docId
            if (item.kind !== "Carte WEFAX") {
                docsModel.setProperty(j, "included", true)
                newIncluded[iid] = true
            } else if (!seen[item.station]) {
                seen[item.station] = true
                docsModel.setProperty(j, "included", true)
                newIncluded[iid] = true
            }
        }
        root.includedIds = newIncluded
    }

    function compile() {
        root.compiling = true
        var ids = []
        for (var k in root.includedIds) {
            if (root.includedIds[k]) ids.push(k)
        }
        appBridge.compileBulletin(ids, root.zone)
        innerTabs.currentIndex = 1  // aller à l'onglet Bulletin
    }

    ListModel { id: docsModel }

    Timer {
        id: savedTimer
        interval: 3000
        onTriggered: root.savedVisible = false
    }

    // ── Sous-onglets ──────────────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill:    parent
        anchors.margins: 8
        spacing:         6

        // Titre + zone
        RowLayout {
            spacing: 8
            Text {
                text:  "📋 Poste Météo & Bulletin"
                color: "#b0c2d4"
                font { pixelSize: 14; bold: true }
            }
            Item { Layout.fillWidth: true }
            Text { text: "Zone :"; color: "#607890"; font.pixelSize: 11 }
            Rectangle {
                width: 220; height: 26
                radius: 4; color: "#0a1520"
                border.color: "#2a5080"; border.width: 1
                TextField {
                    anchors { fill: parent; margins: 3 }
                    placeholderText: "ex. Méditerranée occidentale"
                    color: "#b0c2d4"; font.pixelSize: 11
                    background: Rectangle { color: "transparent" }
                    onTextChanged: root.zone = text
                }
            }
        }

        // Barre de navigation des sous-onglets
        Row {
            spacing: 2
            Repeater {
                model: ["1 · Réceptions 24 h", "2 · Bulletin", "3 · Statistiques"]
                delegate: Rectangle {
                    width:  implicitWidth + 24
                    height: 30
                    radius: 4
                    color:  innerTabs.currentIndex === index ? "#1e3a5f" : "#0a1520"
                    border.color: innerTabs.currentIndex === index ? "#3a7abf" : "#1e3a5f"
                    border.width: 1
                    Text {
                        anchors.centerIn: parent
                        text:  modelData
                        color: innerTabs.currentIndex === index ? "#7ec8e3" : "#607890"
                        font.pixelSize: 11
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape:  Qt.PointingHandCursor
                        onClicked:    innerTabs.currentIndex = index
                    }
                }
            }
        }

        // Contenu des sous-onglets
        StackLayout {
            id: innerTabs
            Layout.fillWidth:  true
            Layout.fillHeight: true

            // ── 1 : RÉCEPTIONS 24 H ──────────────────────────────────────────
            Rectangle {
                color: "#0a1520"; radius: 6
                border.color: "#1e3a5f"; border.width: 1

                ColumnLayout {
                    anchors { fill: parent; margins: 8 }
                    spacing: 6

                    Text {
                        text:  "Cocher ☑ les documents à inclure dans le bulletin. Double-clic : ouvre le fichier."
                        color: "#607890"; font.pixelSize: 10
                    }

                    // En-tête de la liste
                    Rectangle {
                        Layout.fillWidth: true
                        height: 24
                        color: "#091628"
                        border.color: "#1e3a5f"; border.width: 1
                        radius: 3
                        Row {
                            anchors { fill: parent; leftMargin: 6 }
                            spacing: 0
                            Repeater {
                                model: [
                                    { label: "☑",        w: 32  },
                                    { label: "UTC",       w: 100 },
                                    { label: "Type",      w: 110 },
                                    { label: "Station",   w: 80  },
                                    { label: "kHz",       w: 70  },
                                    { label: "Fiabilité", w: 100 },
                                    { label: "État",      w: 90  },
                                    { label: "Contenu",   w: 0   },
                                ]
                                delegate: Text {
                                    width:  modelData.w > 0 ? modelData.w : docList.width - 582
                                    height: 24
                                    text:   modelData.label
                                    color:  "#607890"
                                    font { pixelSize: 10; bold: true }
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }
                    }

                    ListView {
                        id:   docList
                        Layout.fillWidth:  true
                        Layout.fillHeight: true
                        model:  docsModel
                        clip:   true
                        spacing: 1

                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            width:  docList.width
                            height: 28
                            color: {
                                if (dMa.containsMouse) return "#152638"
                                return index % 2 === 0 ? "#0a1520" : "#091628"
                            }
                            radius: 2

                            Row {
                                anchors { fill: parent; leftMargin: 6 }
                                spacing: 0

                                // Checkbox
                                Text {
                                    width: 32; height: parent.height
                                    text:  model.included ? "☑" : "☐"
                                    color: model.included ? "#7ec8e3" : "#607890"
                                    font.pixelSize: 13
                                    verticalAlignment: Text.AlignVCenter
                                }
                                // UTC
                                Text { width: 100; height: parent.height; text: model.start_utc
                                    color: "#a0b8d0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight }
                                // Type (couleur selon kind)
                                Text { width: 110; height: parent.height; text: model.kind
                                    color: model.kind === "Carte WEFAX" ? "#60c4a0"
                                           : model.kind === "NAVTEX" ? "#c4a060" : "#c4c060"
                                    font.pixelSize: 10; verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight }
                                // Station
                                Text { width: 80; height: parent.height; text: model.station
                                    color: "#a0b8d0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight }
                                // kHz
                                Text { width: 70; height: parent.height; text: model.freq_khz
                                    color: "#a0b8d0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter }
                                // Fiabilité
                                Text {
                                    width: 100; height: parent.height
                                    text: model.reliability
                                    color: {
                                        var r = parseInt(model.reliability)
                                        if (isNaN(r)) return "#607890"
                                        return r >= 70 ? "#60c480" : r >= 50 ? "#c4c060" : "#c46060"
                                    }
                                    font.pixelSize: 10; verticalAlignment: Text.AlignVCenter
                                }
                                // État
                                Text { width: 90; height: parent.height; text: model.status
                                    color: "#a0b8d0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight }
                                // Contenu / product
                                Text {
                                    width:  docList.width - 582
                                    height: parent.height
                                    text:   model.product
                                    color:  "#607890"; font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }

                            MouseArea {
                                id: dMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape:  Qt.PointingHandCursor
                                onClicked: {
                                    // Toggle inclusion
                                    var newVal = !model.included
                                    docsModel.setProperty(index, "included", newVal)
                                    var updated = Object.assign({}, root.includedIds)
                                    if (newVal) updated[model.docId] = true
                                    else        delete updated[model.docId]
                                    root.includedIds = updated
                                }
                                onDoubleClicked: {
                                    // Ouvre le premier fichier de la liste (image ou texte)
                                    if (model.files && model.files.length > 0) {
                                        Qt.openUrlExternally("file:///" + model.files[0])
                                    }
                                }
                            }
                        }

                        // Vide
                        Text {
                            anchors.centerIn: parent
                            visible: docsModel.count === 0 && !root.loadingDocs
                            text:    "Aucune réception dans les dernières 24 h\n(dossier de travail vide ou non configuré)"
                            color:   "#3a5a7a"; font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                        }

                        BusyIndicator {
                            anchors.centerIn: parent
                            visible: root.loadingDocs
                            running: root.loadingDocs
                        }
                    }

                    // Barre d'actions
                    RowLayout {
                        spacing: 8
                        Button {
                            text: "↻ Actualiser"
                            onClicked: root.refreshDocs()
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: docsModel.count + " document(s) — "
                                  + Object.keys(root.includedIds).length + " sélectionné(s)"
                            color: "#607890"; font.pixelSize: 10
                            verticalAlignment: Text.AlignVCenter
                        }
                        Button {
                            text:    "➜ Compiler le bulletin avec la sélection"
                            enabled: !root.compiling
                            highlighted: true
                            onClicked: root.compile()
                        }
                    }
                }
            }

            // ── 2 : BULLETIN ─────────────────────────────────────────────────
            Rectangle {
                color: "#0a1520"; radius: 6
                border.color: "#1e3a5f"; border.width: 1

                ColumnLayout {
                    anchors { fill: parent; margins: 8 }
                    spacing: 6

                    // Barre outils
                    RowLayout {
                        spacing: 6
                        Button {
                            text:    "↻ Recompiler"
                            enabled: !root.compiling
                            onClicked: root.compile()
                        }
                        Button {
                            text: "📋 Copier"
                            onClicked: {
                                bulletinEdit.selectAll()
                                bulletinEdit.copy()
                            }
                        }
                        Button {
                            text: "💾 Enregistrer"
                            onClicked: appBridge.saveBulletinText(bulletinEdit.text, root.zone)
                        }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            width:  180; height: 26
                            radius: 4
                            color:  root.savedVisible ? "#064e35" : "transparent"
                            border.color: root.savedVisible ? "#10b981" : "transparent"
                            visible: root.savedVisible
                            Text {
                                anchors.centerIn: parent
                                text:  "✅ Bulletin enregistré"
                                color: "#10b981"; font.pixelSize: 11
                            }
                            Behavior on color { ColorAnimation { duration: 300 } }
                        }
                        BusyIndicator {
                            width: 24; height: 24
                            visible: root.compiling
                            running: root.compiling
                        }
                    }

                    // Éditeur du bulletin
                    ScrollView {
                        Layout.fillWidth:  true
                        Layout.fillHeight: true
                        clip: true
                        TextArea {
                            id:      bulletinEdit
                            text:    root.bulletinText.length > 0
                                     ? root.bulletinText
                                     : "Cliquez sur « Compiler le bulletin » pour générer le bulletin opérateur."
                            color:   "#c0d8f0"
                            font { pixelSize: 12; family: "Consolas, 'Courier New', monospace" }
                            wrapMode: TextArea.Wrap
                            background: Rectangle { color: "#0b1220" }
                            padding: 10
                        }
                    }
                }
            }

            // ── 3 : STATISTIQUES ─────────────────────────────────────────────
            Rectangle {
                color: "#0a1520"; radius: 6
                border.color: "#1e3a5f"; border.width: 1

                ColumnLayout {
                    anchors { fill: parent; margins: 8 }
                    spacing: 6

                    RowLayout {
                        Text {
                            text:  "Statistiques de réception — 24 h"
                            color: "#b0c2d4"; font.pixelSize: 13
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: "↻ Actualiser"
                            onClicked: root.compile()
                        }
                    }

                    ScrollView {
                        Layout.fillWidth:  true
                        Layout.fillHeight: true
                        clip: true
                        TextArea {
                            id:      statsView
                            text:    root.statsText.length > 0
                                     ? root.statsText
                                     : "Compilez le bulletin pour afficher les statistiques."
                            color:   "#a0b8d0"
                            font { pixelSize: 11; family: "Consolas, 'Courier New', monospace" }
                            wrapMode: TextArea.NoWrap
                            readOnly: true
                            background: Rectangle { color: "#0b1220" }
                            padding: 10
                        }
                    }
                }
            }
        }
    }
}
