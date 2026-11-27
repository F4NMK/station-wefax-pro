import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

/*
 * HelpDialog.qml — Aide intégrée contextuelle (port de HelpMixin Tkinter 2.14)
 *
 * Instancier dans main.qml :
 *   HelpDialog { id: helpDialog }
 *
 * Ouvrir sur F1 :
 *   Shortcut { sequence: "F1"; onActivated: helpDialog.openTopic("") }
 *
 * Ouvrir sur un topic précis :
 *   helpDialog.openTopic("WEFAX_DECODE")
 */
Popup {
    id: root
    width:   Math.min(parent.width  * 0.90, 980)
    height:  Math.min(parent.height * 0.88, 720)
    anchors.centerIn: parent
    modal:   true
    focus:   true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    property var    topics:          []
    property string selectedKey:     ""
    property string selectedContent: ""
    property string searchText:      ""

    function openTopic(key) {
        root.open()
        if (root.topics.length === 0) {
            root.topics = appBridge.listHelpTopics()
            topicsModel.clear()
            for (var i = 0; i < root.topics.length; i++) {
                topicsModel.append(root.topics[i])
            }
        }
        if (key.length > 0) {
            root.selectTopic(key)
        } else if (root.topics.length > 0 && root.selectedKey === "") {
            root.selectTopic(root.topics[0].key)
        }
    }

    function selectTopic(key) {
        root.selectedKey     = key
        root.selectedContent = appBridge.getHelpContent(key)
        helpText.text        = root.selectedContent
        // Scroll liste vers la rubrique sélectionnée
        for (var i = 0; i < topicsModel.count; i++) {
            if (topicsModel.get(i).key === key) {
                topicsList.positionViewAtIndex(i, ListView.Contain)
                break
            }
        }
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

    background: Rectangle {
        color:        "#0d1b2a"
        radius:       10
        border.color: "#1e3a5f"
        border.width: 1
    }

    ColumnLayout {
        anchors.fill:    parent
        anchors.margins: 2
        spacing: 0

        // ── En-tête ───────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 40
            color: "#091628"
            radius: 10

            RowLayout {
                anchors { fill: parent; margins: 10 }
                Text {
                    text:  "📚 Aide intégrée — Station WEFAX PRO"
                    color: "#b0c2d4"
                    font { pixelSize: 14; bold: true }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 28; height: 28; radius: 4
                    color: closeHover.containsMouse ? "#2a3a52" : "transparent"
                    Text { anchors.centerIn: parent; text: "✕"; color: "#607890"; font.pixelSize: 14 }
                    MouseArea {
                        id: closeHover; anchors.fill: parent
                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }
        }

        // ── Corps : index + contenu ───────────────────────────────────────
        RowLayout {
            Layout.fillWidth:  true
            Layout.fillHeight: true
            Layout.margins:    8
            spacing:           8

            // Colonne gauche : liste des rubriques
            ColumnLayout {
                Layout.preferredWidth: 240
                Layout.fillHeight:     true
                spacing:               6

                // Champ recherche
                Rectangle {
                    Layout.fillWidth: true
                    height:           32; radius: 4
                    color: "#0a1520"
                    border.color: "#2a5080"; border.width: 1
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
                    color: "#0a1520"; radius: 6
                    border.color: "#1e3a5f"; border.width: 1
                    clip: true

                    ListView {
                        id: topicsList
                        anchors.fill: parent; anchors.margins: 2
                        model:   topicsModel
                        spacing: 1; clip: true
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            width:  topicsList.width; height: 32
                            color: {
                                if (root.selectedKey === model.key) return "#1e3a5f"
                                if (tMa.containsMouse)             return "#152638"
                                return "transparent"
                            }
                            radius: 3
                            Text {
                                anchors {
                                    left: parent.left; leftMargin: 10
                                    right: parent.right; rightMargin: 6
                                    verticalCenter: parent.verticalCenter
                                }
                                text:  model.title
                                color: root.selectedKey === model.key ? "#7ec8e3" : "#a0b8d0"
                                font.pixelSize: 11; elide: Text.ElideRight
                            }
                            MouseArea {
                                id: tMa; anchors.fill: parent
                                hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked:    root.selectTopic(model.key)
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: topicsModel.count === 0
                            text: "Aucune rubrique"
                            color: "#3a5a7a"; font.pixelSize: 11
                        }
                    }
                }
            }

            // Colonne droite : contenu
            Rectangle {
                Layout.fillWidth:  true
                Layout.fillHeight: true
                color: "#0a1520"; radius: 6
                border.color: "#1e3a5f"; border.width: 1

                ScrollView {
                    anchors { fill: parent; margins: 12 }
                    clip: true
                    TextArea {
                        id:         helpText
                        text:       "Sélectionner une rubrique ou appuyer sur F1."
                        color:      "#c0d8f0"
                        font { pixelSize: 12; family: "Segoe UI, Helvetica, Arial, sans-serif" }
                        wrapMode:   TextArea.Wrap
                        readOnly:   true
                        textFormat: TextArea.PlainText
                        background: Rectangle { color: "transparent" }
                        padding: 4
                    }
                }
            }
        }

        // ── Pied de page ──────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 32; color: "#091628"; radius: 10
            Text {
                anchors.centerIn: parent
                text:  "F1 : ouvrir/fermer  ·  Échap : fermer"
                color: "#3a5a7a"; font.pixelSize: 10
            }
        }
    }
}
