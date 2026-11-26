import QtQuick
import QtQuick.Controls as QC
import ".." as T

/*
 * DropDown.qml — Sélecteur déroulant personnalisé (évite les warnings de style natif)
 *
 * Propriétés :
 *   model       : list<string>  — liste des choix
 *   currentText : string        — valeur sélectionnée (lecture/écriture)
 *   enabled     : bool (hérité)
 *
 * Signaux :
 *   selected(string text)       — émis quand l'utilisateur choisit un élément
 */
Rectangle {
    id: root

    property var    model:       []
    property string currentText: model.length > 0 ? model[0] : ""
    property int    currentIndex: 0

    signal selected(string text)

    implicitWidth:  120
    implicitHeight: 26
    radius:         T.Theme.radiusSm
    color:          T.Theme.bgSurface
    border.color:   dropArea.containsMouse ? T.Theme.accentBorder : T.Theme.border
    border.width:   1
    clip:           true

    opacity: enabled ? 1.0 : 0.4

    // Texte courant
    Text {
        anchors {
            left:            parent.left
            leftMargin:      8
            verticalCenter:  parent.verticalCenter
            right:           arrow.left
            rightMargin:     4
        }
        text:            root.currentText
        color:           T.Theme.textPrimary
        font.family:     T.Theme.fontMono
        font.pixelSize:  T.Theme.fontSizeSm
        elide:           Text.ElideRight
    }

    // Flèche
    Text {
        id: arrow
        anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
        text:            popup.visible ? "▴" : "▾"
        color:           T.Theme.textDim
        font.pixelSize:  T.Theme.fontSizeXs
    }

    // Clic ouvre le popup
    HoverHandler { id: dropArea }
    TapHandler {
        enabled: root.enabled
        onTapped: popup.visible ? popup.close() : popup.open()
    }

    // Popup liste
    QC.Popup {
        id: popup
        y:       root.height + 2
        width:   Math.max(root.width, 140)
        padding: 0
        closePolicy: QC.Popup.CloseOnEscape | QC.Popup.CloseOnPressOutside

        background: Rectangle {
            color:        T.Theme.bgSurface
            radius:       T.Theme.radiusSm
            border.color: T.Theme.border
            border.width: 1
        }

        contentItem: Column {
            spacing: 0

            Repeater {
                model: root.model

                delegate: Rectangle {
                    width:  popup.width
                    height: 26
                    color:  itemHov.hovered ? Qt.rgba(1,1,1,0.07) : "transparent"

                    HoverHandler { id: itemHov }

                    Text {
                        anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                        text:            modelData
                        color:           modelData === root.currentText ? T.Theme.accent : T.Theme.textPrimary
                        font.family:     T.Theme.fontMono
                        font.pixelSize:  T.Theme.fontSizeSm
                    }

                    TapHandler {
                        onTapped: {
                            root.currentText  = modelData
                            root.currentIndex = index
                            root.selected(modelData)
                            popup.close()
                        }
                    }
                }
            }
        }
    }
}
