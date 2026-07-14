package com.icar.musiccar

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.min

/** Renders only the structured bounding boxes carried by bridge v3; no image bytes are assumed. */
class YoloOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {
    var onTrackSelected: ((Int) -> Unit)? = null
    private var frame = YoloFrame()
    private var selectedTrackId: Int? = null
    private val framePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(38, 59, 66)
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }
    private val boxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 28f
    }
    private val messagePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(177, 197, 204)
        textSize = 30f
        textAlign = Paint.Align.CENTER
    }

    fun showFrame(value: YoloFrame, selected: Int?) {
        frame = value
        selectedTrackId = selected
        contentDescription = when {
            value.error != null -> "YOLO 异常：${value.error}"
            value.detections.isEmpty() -> "YOLO 当前未识别到目标"
            else -> "YOLO 识别到 ${value.detections.size} 个目标"
        }
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val area = contentArea() ?: run {
            return
        }
        frame.detections.filter(YoloDetection::hasBox).forEach { detection ->
            val rect = detectionRect(detection, area)
            val selected = detection.trackId != null && detection.trackId == selectedTrackId
            boxPaint.color = when {
                selected -> Color.rgb(255, 193, 7)
                detection.isPerson -> Color.rgb(0, 214, 170)
                else -> Color.rgb(69, 170, 242)
            }
            canvas.drawRect(rect, boxPaint)
            val track = detection.trackId?.let { " #$it" }.orEmpty()
            val distance = detection.distanceMeters?.let { " %.2fm".format(it) }.orEmpty()
            val label = "${detection.label}$track ${(detection.confidence * 100).toInt()}%$distance"
            canvas.drawText(label, rect.left.coerceAtLeast(area.left) + 4f, (rect.top - 7f).coerceAtLeast(area.top + 28f), labelPaint)
        }
        if (frame.detections.isEmpty()) {
            canvas.drawText(frame.error ?: "当前帧未检测到目标", width / 2f, height / 2f, messagePaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action != MotionEvent.ACTION_UP) return true
        val area = contentArea() ?: return true
        val hit = frame.detections.asSequence()
            .filter { it.trackId != null && it.hasBox && detectionRect(it, area).contains(event.x, event.y) }
            .minByOrNull { (it.xMax - it.xMin) * (it.yMax - it.yMin) }
        hit?.trackId?.let {
            selectedTrackId = it
            onTrackSelected?.invoke(it)
            invalidate()
            performClick()
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun contentArea(): RectF? {
        if (frame.imageWidth <= 0 || frame.imageHeight <= 0 || width <= 0 || height <= 0) return null
        val scale = min(width.toFloat() / frame.imageWidth, height.toFloat() / frame.imageHeight)
        val renderedWidth = frame.imageWidth * scale
        val renderedHeight = frame.imageHeight * scale
        val left = (width - renderedWidth) / 2f
        val top = (height - renderedHeight) / 2f
        return RectF(left, top, left + renderedWidth, top + renderedHeight)
    }

    private fun detectionRect(detection: YoloDetection, area: RectF): RectF {
        val xScale = area.width() / frame.imageWidth
        val yScale = area.height() / frame.imageHeight
        return RectF(
            area.left + detection.xMin.toFloat() * xScale,
            area.top + detection.yMin.toFloat() * yScale,
            area.left + detection.xMax.toFloat() * xScale,
            area.top + detection.yMax.toFloat() * yScale
        )
    }
}
