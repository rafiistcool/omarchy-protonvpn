import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property real iconSize: Style.font.icon
  property color color: Color.foreground
  property color badgeColor: Color.urgent
  property bool crossed: false
  property bool warning: false

  width: iconSize
  height: iconSize
  implicitWidth: iconSize
  implicitHeight: iconSize

  // Proton mark: a filled triangle matching the official shield silhouette.
  Canvas {
    id: mark
    anchors.fill: parent
    onPaint: {
      var ctx = getContext("2d")
      ctx.reset()
      var w = width
      var h = height
      ctx.fillStyle = root.color
      ctx.beginPath()
      ctx.moveTo(w * 0.50, h * 0.94)
      ctx.lineTo(w * 0.94, h * 0.24)
      ctx.quadraticCurveTo(w * 0.98, h * 0.12, w * 0.82, h * 0.10)
      ctx.lineTo(w * 0.10, h * 0.16)
      ctx.quadraticCurveTo(w * -0.02, h * 0.18, w * 0.08, h * 0.34)
      ctx.closePath()
      ctx.fill()
    }
  }

  onColorChanged: mark.requestPaint()
  onWidthChanged: mark.requestPaint()
  onHeightChanged: mark.requestPaint()
  Component.onCompleted: mark.requestPaint()

  Rectangle {
    visible: root.crossed
    anchors.centerIn: parent
    width: parent.width * 1.18
    height: Math.max(2, parent.height * 0.14)
    radius: height / 2
    color: root.color
    rotation: -45
  }

  BorderSurface {
    visible: root.warning
    width: Math.max(7, parent.width * 0.42)
    height: width
    radius: width / 2
    color: root.badgeColor
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    borderSpec: Border.flat(Color.popups.background, 1)

    Text {
      anchors.centerIn: parent
      text: "!"
      color: Color.background
      font.family: Style.font.family
      font.pixelSize: Math.max(6, parent.height * 0.72)
      font.bold: true
    }
  }
}
