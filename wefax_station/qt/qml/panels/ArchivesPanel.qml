import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "." as T

/*
 * ArchivesPanel.qml — Historique et consultation des cartes WEFAX
 *
 * Fonctionnalités portées depuis ArchivesMixin (Tkinter 2.14) :
 *   - Liste des cartes reçues (tri date desc) avec taille Ko
 *   - Consultation d'une carte par clic
 *   - Export signé (cartouche opérateur)
 *   - Suppression avec confirmation
 *   - Ouverture du dossier archives
 *   - Rafraîchissement manuel et automatique
 */
Rectangle {
    id: root
    color: "#0d1b2a"

    // ── Données ──────────────────────────────────────────────────────────────
    property var    archivesList:    []
    property string selectedPath:    ""
    property string selectedName:    ""
    property bool   loading:         false

    // ── Connexions AppBridge ─────────────────────────────────────────────────
    Connections {
        target: appBridge

        function onArchivesLoaded(files) {
            root.archivesList = files
            root.loading      = false
            archivesModel.clear()
            for (var i = 0; i < files.length; i++) {
                archivesModel.append(files[i])
            }
        }

        function onExportDone(path) {
            exportDoneMsg.text    = "Export signé : " + path.split("/").pop()
            exportDoneMsg.visible = true
            exportMsgTimer.restart()
        }

        function onImageCompleted(path) {
            // Rafraîchir automatiquement quand une carte est reçue
            root.refresh()
        }
    }

    // ── Initialisation ───────────────────────────────────────────────────────
    Component.onCompleted: {
        root.refresh()
    }

    function refresh() {
        root.loading = true
        appBridge.refreshArchives()
    }

    // ── Modèle de liste ──────────────────────────────────────────────────────
    ListModel {
        id: archivesModel
    }

    // ── Layout principal ─────────────────────────────────────────────────────
    RowLayout {
        anchors.fill:    parent
        anchors.margins: 8
        spacing:         8

        // ── Colonne gauche : liste ────────────────────────────────────────
        ColumnLayout {
            Layout.preferredWidth: 380
            Layout.fillHeight:     true
            spacing:               6

            // Titre + boutons
            RowLayout {
                Layout.fillWidth: true
                spacing:          6

                Text {
                    text:  "🗂️ Historique des cartes"
                    color: "#b0c2d4"
                    font { pixelSize: 14; bold: true }
                }

                Item { Layout.fillWidth: true }

                // Rafraîchir
                Rectangle {
                    width:  32; height: 28
                    radius: 4
                    color:  refreshMa.containsMouse ? "#1e3a5f" : "#152638"
                    border.color: "#2a5080"; border.width: 1
                    Text {
                        anchors.centerIn: parent
                        text: "🔄"
                        font.pixelSize: 14
                    }
                    MouseArea {
                        id: refreshMa
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked:    root.refresh()
                        cursorShape:  Qt.PointingHandCursor
                    }
                    ToolTip.visible: refreshMa.containsMouse
                    ToolTip.text:    "Rafraîchir la liste"
                }

                // Ouvrir dossier
                Rectangle {
                    width:  32; height: 28
                    radius: 4
                    color:  folderMa.containsMouse ? "#1e3a5f" : "#152638"
                    border.color: "#2a5080"; border.width: 1
                    Text {
                        anchors.centerIn: parent
                        text: "📁"
                        font.pixelSize: 14
                    }
                    MouseArea {
                        id: folderMa
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked:    appBridge.openArchives()
                        cursorShape:  Qt.PointingHandCursor
                    }
                    ToolTip.visible: folderMa.containsMouse
                    ToolTip.text:    "Ouvrir le dossier archives"
                }
            }

            // Compteur
            Text {
                visible:         !root.loading
                text:            archivesModel.count + " carte(s)"
                color:           "#607890"
                font.pixelSize:  11
            }

            // Indicateur chargement
            Text {
                visible:         root.loading
                text:            "Chargement…"
                color:           "#607890"
                font.pixelSize:  11
            }

            // Liste des cartes
            Rectangle {
                Layout.fillWidth:  true
                Layout.fillHeight: true
                color:             "#0a1520"
                radius:            6
                border.color:      "#1e3a5f"
                border.width:      1
                clip:              true

                ListView {
                    id:          archivesList
                    anchors.fill: parent
                    anchors.margins: 2
                    model:       archivesModel
                    spacing:     1
                    clip:        true

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: Rectangle {
                        width:  archivesList.width
                        height: 48
                        color: {
                            if (root.selectedPath === model.path)
                                return "#1e3a5f"
                            if (itemMa.containsMouse)
                                return "#152638"
                            return index % 2 === 0 ? "#0d1b2a" : "#0a1520"
                        }
                        radius: 3

                        RowLayout {
                            anchors {
                                left: parent.left; right: parent.right
                                verticalCenter: parent.verticalCenter
                                leftMargin: 10; rightMargin: 6
                            }
                            spacing: 8

                            // Icône partielle vs complète
                            Text {
                                text: model.partial ? "⚠️" : "🗺️"
                                font.pixelSize: 16
                            }

                            // Nom + taille
                            Column {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    width:          parent.width
                                    text:           model.name
                                    color:          root.selectedPath === model.path ? "#7ec8e3" : "#b0c2d4"
                                    font.pixelSize: 11
                                    elide:          Text.ElideMiddle
                                }
                                Text {
                                    text:           model.size_kb + " Ko"
                                    color:          "#4a6a8a"
                                    font.pixelSize: 10
                                }
                            }
                        }

                        MouseArea {
                            id:          itemMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape:  Qt.PointingHandCursor
                            onClicked: {
                                root.selectedPath = model.path
                                root.selectedName = model.name
                                // Charger l'image dans le viewer
                                imageViewer.source = "file:///" + model.path.replace(/\\/g, "/")
                            }
                        }
                    }

                    // Placeholder vide
                    Text {
                        anchors.centerIn: parent
                        visible:          archivesModel.count === 0 && !root.loading
                        text:             "Aucune carte dans les archives"
                        color:            "#3a5a7a"
                        font.pixelSize:   13
                    }
                }
            }
        }

        // ── Colonne droite : viewer + actions ─────────────────────────────
        ColumnLayout {
            Layout.fillWidth:  true
            Layout.fillHeight: true
            spacing:           6

            // Barre d'actions
            RowLayout {
                Layout.fillWidth: true
                spacing:          6

                Text {
                    text:            root.selectedName.length > 0
                                     ? "📋 " + root.selectedName
                                     : "📋 Sélectionner une carte dans la liste"
                    color:           "#b0c2d4"
                    font.pixelSize:  12
                    elide:           Text.ElideMiddle
                    Layout.fillWidth: true
                }

                // Bouton Export signé
                Rectangle {
                    width:   140; height: 30
                    radius:  5
                    visible: root.selectedPath.length > 0
                    color:   exportMa.containsMouse ? "#2a6a3a" : "#1a4a2a"
                    border.color: "#3a8a4a"; border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text:  "🖊️ Exporter signé"
                        color: "#a0e0a0"
                        font.pixelSize: 11
                    }
                    MouseArea {
                        id: exportMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape:  Qt.PointingHandCursor
                        onClicked:    appBridge.exportSignedImage(root.selectedPath)
                    }
                    ToolTip.visible: exportMa.containsMouse
                    ToolTip.text:    "Exporte avec cartouche opérateur (PNG signé)"
                }

                // Bouton Supprimer
                Rectangle {
                    width:   36; height: 30
                    radius:  5
                    visible: root.selectedPath.length > 0
                    color:   deleteMa.containsMouse ? "#6a1a1a" : "#3a0a0a"
                    border.color: "#8a2a2a"; border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text:  "🗑️"
                        font.pixelSize: 14
                    }
                    MouseArea {
                        id: deleteMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape:  Qt.PointingHandCursor
                        onClicked:    deleteDialog.open()
                    }
                    ToolTip.visible: deleteMa.containsMouse
                    ToolTip.text:    "Supprimer cette carte"
                }
            }

            // Message export
            Rectangle {
                id:      exportDoneMsg
                visible: false
                height:  28
                Layout.fillWidth: true
                color:   "#0a2a0a"
                radius:  4
                border.color: "#3a8a3a"; border.width: 1

                Text {
                    id:                 exportDoneTxt
                    anchors.centerIn:   parent
                    color:              "#70e070"
                    font.pixelSize:     11
                }

                Timer {
                    id:       exportMsgTimer
                    interval: 5000
                    onTriggered: exportDoneMsg.visible = false
                }
            }

            // Viewer image
            Rectangle {
                Layout.fillWidth:  true
                Layout.fillHeight: true
                color:             "#050e18"
                radius:            6
                border.color:      "#1e3a5f"
                border.width:      1
                clip:              true

                // Placeholder quand rien n'est sélectionné
                Text {
                    anchors.centerIn: parent
                    visible:          root.selectedPath.length === 0
                    text:             "Sélectionner une carte\npour la visualiser"
                    color:            "#2a4a6a"
                    font.pixelSize:   15
                    horizontalAlignment: Text.AlignHCenter
                }

                // Image affichée
                Image {
                    id:              imageViewer
                    anchors.fill:    parent
                    anchors.margins: 4
                    fillMode:        Image.PreserveAspectFit
                    visible:         root.selectedPath.length > 0
                    asynchronous:    true
                    cache:           false

                    // Spinner pendant chargement
                    BusyIndicator {
                        anchors.centerIn: parent
                        running:          imageViewer.status === Image.Loading
                    }

                    // Erreur de chargement
                    Text {
                        anchors.centerIn: parent
                        visible:          imageViewer.status === Image.Error
                        text:             "Impossible d'afficher l'image"
                        color:            "#8a3a3a"
                        font.pixelSize:   12
                    }
                }

                // Zoom info
                Text {
                    anchors {
                        bottom: parent.bottom
                        right:  parent.right
                        margins: 6
                    }
                    visible:         imageViewer.status === Image.Ready
                    text:            imageViewer.sourceSize.width + "×" + imageViewer.sourceSize.height + " px"
                    color:           "#3a6a9a"
                    font.pixelSize:  10
                }
            }

            // Légende
            Text {
                visible:         root.selectedPath.length > 0
                text:            "⚠️ = carte partielle (réception interrompue)"
                color:           "#4a6a8a"
                font.pixelSize:  10
            }
        }
    }

    // ── Dialogue confirmation suppression ────────────────────────────────────
    Dialog {
        id:               deleteDialog
        title:            "Confirmer la suppression"
        modal:            true
        anchors.centerIn: parent
        width:            360

        background: Rectangle {
            color:        "#0d1b2a"
            radius:       8
            border.color: "#2a5080"
            border.width: 1
        }

        Text {
            text:           "Supprimer définitivement :\n" + root.selectedName + " ?"
            color:          "#b0c2d4"
            font.pixelSize: 12
            wrapMode:       Text.WordWrap
            width:          parent.width
        }

        footer: DialogButtonBox {
            Button {
                text:              "Supprimer"
                DialogButtonBox.buttonRole: DialogButtonBox.DestructiveRole
                contentItem: Text {
                    text:  parent.text
                    color: "#e07070"
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: 12
                }
                background: Rectangle {
                    color:        parent.pressed ? "#6a1a1a" : "#3a0a0a"
                    radius:       4
                    border.color: "#8a2a2a"
                    border.width: 1
                }
                onClicked: {
                    appBridge.deleteArchiveFile(root.selectedPath)
                    root.selectedPath = ""
                    root.selectedName = ""
                    imageViewer.source = ""
                    deleteDialog.close()
                }
            }
            Button {
                text:              "Annuler"
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
                contentItem: Text {
                    text:  parent.text
                    color: "#b0c2d4"
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: 12
                }
                background: Rectangle {
                    color:        parent.pressed ? "#1e3a5f" : "#152638"
                    radius:       4
                    border.color: "#2a5080"
                    border.width: 1
                }
                onClicked: deleteDialog.close()
            }
        }
    }

    // Timer autoreload toutes les 2 min
    Timer {
        interval:  120000
        running:   true
        repeat:    true
        onTriggered: root.refresh()
    }
}
