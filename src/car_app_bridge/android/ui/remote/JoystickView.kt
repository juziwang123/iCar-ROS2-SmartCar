// 虚拟摇杆 —— 自定义 View
// 手指拖动计算线速度（Y 轴）和角速度（X 轴），松手自动回调停止

package com.icar.app.ui.remote

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.min

class JoystickView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    var onMove: ((linear: Double, angular: Double) -> Unit)? = null
    var onRelease: (() -> Unit)? = null

    private var pointerId = -1
    private var centerX = 0f
    private var centerY = 0f
    private var radius = 0f
    private var knobX = 0f
    private var knobY = 0f

    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#33FFFFFF")
        style = Paint.Style.FILL
    }
    private val knobPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#CC4488FF")
        style = Paint.Style.FILL
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        centerX = w / 2f
        centerY = h / 2f
        radius = min(w, h) / 2f * 0.75f
        knobX = centerX
        knobY = centerY
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawCircle(centerX, centerY, radius, bgPaint)
        canvas.drawCircle(knobX, knobY, radius * 0.35f, knobPaint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                pointerId = event.getPointerId(event.actionIndex)
                updateKnob(event)
            }
            MotionEvent.ACTION_MOVE -> {
                updateKnob(event)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                pointerId = -1
                knobX = centerX
                knobY = centerY
                invalidate()
                onRelease?.invoke()
                updateKnob(event)
            }
        }
        return true
    }

    private fun updateKnob(event: MotionEvent) {
        if (pointerId < 0) return
        val idx = event.findPointerIndex(pointerId)
        if (idx < 0) return

        var dx = event.getX(idx) - centerX
        var dy = event.getY(idx) - centerY
        val dist = hypot(dx, dy)
        if (dist > radius) {
            dx = dx / dist * radius
            dy = dy / dist * radius
        }
        knobX = centerX + dx
        knobY = centerY + dy
        invalidate()

        // 计算速度：Y 轴 → 线速度，X 轴 → 角速度
        val linear = -(dy / radius).toDouble().coerceIn(-1.0, 1.0)
        val angular = (dx / radius).toDouble().coerceIn(-1.0, 1.0)

        // 死区
        if (abs(linear) < 0.1 && abs(angular) < 0.1) {
            onRelease?.invoke()
        } else {
            onMove?.invoke(linear * 0.5, angular * 1.0)
        }
    }
}
