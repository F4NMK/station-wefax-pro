import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

/*
 * HelpPanel.qml — Aide intégrée (port de HelpMixin Tkinter 2.14)
 *
 * - Liste des rubriques (depuis HELP_TOPICS_25)
 * - Recherche textuelle
 * - Affichage du contenu de la rubrique sélectionnée
 * - Liens internes [[topic|texte]] reconnus et cliquables
 */
Rectangle {
    id: root
    color: "#0d1b2a"

    property var    topics:          []
    property string selectedKey:     ""
    property string selectedContent: ""
    property string searchText:      ""

    // ── Initialisation ───────────────────────────────────────────────────────
    Component.onCompleted: {
        root.topics = appBridge.listHelpTopics()
        topicsModel.clear()
        for (var i = 0; i < root.topics.length; i++) {
            topicsModel.append(root.topics[i])
        }
        if (root.topics.length > 0) {
            root.selectTopic(root.topics[0].key)
        }
    }

    function selectTopic(key) {
        root.selectedKey     = key
        root.selectedContent = appBridge.getHelpContent(key)
        helpText.text        = root.selectedContent
    }

    function filterTopics() {
        topicsModel.clear()
        var q = root.searchText.toLowerCase()
        for (var i = 0; i < root.topics.length; i++) {
            var t = root.topics[i]
            if (q.length === 0 || t.title.toLowerCase().indexOf(q) >= 0) {
                topicsModel.append(t)
            }
        }
    }

    ListModel { id: topicsModel }

    // ── Layout ───────────────────────────────────────────────────────────────
    RowLayout {
        anchors.fill:    parent
        anchors.margins: 8
        spacing:         8

        // ── Colonne gauche : index des rubriques ──────────────────────────
        ColumnLayout {
            Layout.preferredWidth: 240
            Layout.fillHeight:     true
            spacing:               6

            Text {
                text:  "📚 Aide intégrée"
                color: "#b0c2d4"
                font { pixelSize: 14; bold: true }
            }

            // Champ recherche
            Rectangle {
                Layout.fillWidth: true
                height:           32
                radius:           4
                color:            "#0a1520"
                border.color:     "#2a5080"
                border.width:     1

                RowLayout {
                    anchors { fill: parent; margins: 4 }
                    spacing: 4

                    Text { text: "🔍"; color: "#607890"; font.pixelSize: 12 }

                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        placeholderText:  "Rechercher…"
                        color:            "#b0c2d4"
                        font.pixelSize:   11
                        background:       Rectangle { color: "transparent" }
                        onTextChanged: {
                            root.searchText = text
                            root.filterTopics()
                        }
                    }
                }
            }

            // Liste des rubriques
            Rectangle {
                Layout.fillWidth:  true
                Layout.fillHeight: true
                color:             "#0a1520"
                radius:            6
                border.color:      "#1e3a5f"
                border.width:      1
                clip:              true

                ListView {
                    id:           topicsList
                    anchors.fill: parent
                    anchors.margins: 2
                    model:        topicsModel
                    spacing:      1
                    clip:         true

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: Rectangle {
                        width:  topicsList.width
                        height: 32
                        color: {
                            if (root.selectedKey === model.key)
                                return "#1e3a5f"
                            if (tMa.containsMouse)
                                return "#152638"
                            return "transparent"
                        }
                        radius: 3

                        Text {
                            anchors {
                                left: parent.left
                                verticalCenter: parent.verticalCenter
                                leftMargin: 10
                                right: parent.right
                                rightMargin: 6
                            }
                            text:  model.title
                            color: root.selectedKey === model.key ? "#7ec8e3" : "#a0b8d0"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }

                        MouseArea {
                            id: tMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape:  Qt.PointingHandCursor
                            onClicked:    root.selectTopic(model.key)
                        }
                    }

                    // Vide
                    Text {
                        anchors.centerIn: parent
                        visible:          topicsModel.count === 0
                        text:             "Aucune rubrique trouvée"
                        color:            "#3a5a7a"
                        font.pixelSize:   11
                    }
                }
            }
        }

        // ── Colonne droite : contenu de la rubrique ───────────────────────
        Rectangle {
            Layout.fillWidth:  true
            Layout.fillHeight: true
            color:             "#0a1520"
            radius:            6
            border.color:      "#1e3a5f"
            border.width:      1

            ColumnLayout {
                anchors { fill: parent; margins: 12 }
                spacing: 6

                ScrollView {
                    Layout.fillWidth:  true
                    Layout.fillHeight: true
                    clip:              true

                    TextArea {
                        id:         helpText
                        text:       "Sélectionner une rubrique dans la liste."
                        color:      "#c0d8f0"
                        font.pixelSize: 12
                        font.family:    "Segoe UI, Helvetica, Arial, sans-serif"
                        wrapMode:   TextArea.Wrap
                        readOnly:   true
                        textFormat: TextArea.PlainText
                        background: Rectangle { color: "transparent" }
                        padding:    4
                    }
                }
            }
        }
    }
}
