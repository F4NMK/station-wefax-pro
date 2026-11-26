import QtQuick
import ".." as T

/*
 * TextInput.qml — Champ de saisie texte personnalisé
 *
 * Propriétés :
 *   text          : string   — valeur courante
 *   placeholder   : string   — texte fantôme si vide
 *   fontFamily    : string   — famille de police
 *   readOnly      : bool
 *   enabled       : bool (hérité)
 *
 * Signaux :
 *   textChanged(string text) — émis à chaque modification
 *   accepted()               — émis à l'appui de Entrée
 */
Rectangle {
    id: root

    property alias  text:        input.text
    property string placeholder: ""
    property string fontFamily:  T.Theme.fontBase
    property alias  readOnly:    input.readOnly

    signal textChanged(string text)
    signal accepted()

    implicitWidth:  100
    implicitHeight: 26
    radius:         T.Theme.radiusSm
    color:          T.Theme.bgSurface
    border.color:   input.activeFocus ? T.Theme.accentBorder : T.Theme.border
    border.width:   1
    clip:           true

    opacity: enabled ? 1.0 : 0.4

    // Placeholder
    Text {
        anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
        text:            root.placeholder
        color:           T.Theme.textDim
        font.family:     root.fontFamily
        font.pixelSize:  T.Theme.fontSizeSm
        visible:         input.text.length === 0 && !input.activeFocus
    }

    TextInput {
        id: input
        anchors {
            left:            parent.left
            right:           parent.right
            leftMargin:      8
            rightMargin:     8
            verticalCenter:  parent.verticalCenter
        }
        color:           T.Theme.textPrimary
        font.family:     root.fontFamily
        font.pixelSize:  T.Theme.fontSizeSm
        selectByMouse:   true
        enabled:         root.enabled

        onTextChanged:   root.textChanged(text)
        Keys.onReturnPressed: root.accepted()
    }

    // Curseur visible au clic
    MouseArea {
        anchors.fill:    parent
        cursorShape:     Qt.IBeamCursor
        onClicked:       input.forceActiveFocus()
    }
}
