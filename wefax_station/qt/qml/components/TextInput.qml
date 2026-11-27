import QtQuick
import ".." as T

/*
 * TextInput.qml — Champ de saisie texte entièrement en QML (pas de style natif)
 *
 * Propriétés :
 *   text          : string   — valeur courante (lecture/écriture)
 *   placeholder   : string   — texte fantôme si vide
 *   fontFamily    : string   — famille de police
 *   readOnly      : bool
 *   enabled       : bool (hérité)
 *
 * Signaux :
 *   textChanged(string text) — émis à chaque frappe, AVEC le texte courant
 *   accepted()               — émis à l'appui de Entrée
 *
 * Usage :
 *   C.TextInput { text: root.gateway; onTextChanged: (t) => root.gateway = t }
 */
Rectangle {
    id: root

    property string text:        ""
    property string placeholder: ""
    property string fontFamily:  T.Theme.fontBase
    property bool   readOnly:    false

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

    // Mise à jour du champ interne quand la propriété externe change
    // (sans boucle : on ne met à jour que si différent)
    onTextChanged: (t) => { if (input.text !== t) input.text = t }

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
        text:            root.text
        color:           T.Theme.textPrimary
        font.family:     root.fontFamily
        font.pixelSize:  T.Theme.fontSizeSm
        selectByMouse:   true
        readOnly:        root.readOnly
        enabled:         root.enabled

        // Remonte vers la propriété publique + émet le signal avec paramètre
        // Guard anti-boucle : on ne réassigne root.text que si différent
        onTextChanged: {
            if (root.text !== input.text) {
                root.text = input.text
                root.textChanged(input.text)
            }
        }
        Keys.onReturnPressed: root.accepted()
    }

    // Curseur visible au clic
    MouseArea {
        anchors.fill: parent
        cursorShape:  Qt.IBeamCursor
        onClicked:    input.forceActiveFocus()
    }
}
