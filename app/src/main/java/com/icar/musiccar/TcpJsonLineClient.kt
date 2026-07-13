package com.icar.musiccar

import android.util.Log
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors

/** Minimal UTF-8 JSON Lines client for the car bridge TCP protocol. */
class TcpJsonLineClient(
    private val onConnected: () -> Unit,
    private val onMessage: (String) -> Unit,
    private val onClosed: (Throwable?) -> Unit
) {
    private val writeLock = Any()
    private val writeExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "icar-tcp-writer").apply { isDaemon = true }
    }

    @Volatile
    private var socket: Socket? = null

    @Volatile
    private var writer: BufferedWriter? = null

    fun connect(host: String, port: Int) {
        Thread {
            var failure: Throwable? = null
            try {
                val clientSocket = Socket()
                clientSocket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
                clientSocket.keepAlive = true
                clientSocket.tcpNoDelay = true
                socket = clientSocket
                writer = BufferedWriter(OutputStreamWriter(clientSocket.getOutputStream(), Charsets.UTF_8))
                Log.d(TAG, "TCP connected to $host:$port")
                onConnected()

                BufferedReader(InputStreamReader(clientSocket.getInputStream(), Charsets.UTF_8)).use { reader ->
                    while (true) {
                        val line = reader.readLine() ?: break
                        if (line.shouldLogWireMessage()) {
                            Log.d(TAG, "TCP received: $line")
                        }
                        if (line.isNotBlank()) onMessage(line)
                    }
                }
            } catch (error: Throwable) {
                failure = error
                Log.e(TAG, "TCP client failed", error)
            } finally {
                closeSocket()
                writeExecutor.shutdownNow()
                Log.d(TAG, "TCP client closed", failure)
                onClosed(failure)
            }
        }.apply {
            name = "icar-tcp-bridge"
            isDaemon = true
            start()
        }
    }

    fun send(jsonLine: String): Boolean {
        return try {
            if (writer == null) {
                Log.w(TAG, "TCP send failed: writer is not available")
                return false
            }
            writeExecutor.execute {
                try {
                    synchronized(writeLock) {
                        val currentWriter = writer ?: return@synchronized
                        Log.d(TAG, "TCP sending: $jsonLine")
                        currentWriter.write(jsonLine)
                        currentWriter.newLine()
                        currentWriter.flush()
                    }
                } catch (error: Throwable) {
                    Log.e(TAG, "TCP async send failed", error)
                    closeSocket()
                    onClosed(error)
                }
            }
            true
        } catch (error: Throwable) {
            Log.e(TAG, "TCP send failed", error)
            false
        }
    }

    fun close() {
        closeSocket()
        writeExecutor.shutdownNow()
    }

    private fun closeSocket() {
        synchronized(writeLock) {
            writer = null
            try {
                socket?.close()
            } catch (_: Throwable) {
                // The reader loop will finish after a local close.
            }
            socket = null
        }
    }

    private companion object {
        private const val TAG = "IcarTcpClient"
        const val CONNECT_TIMEOUT_MS = 15_000
    }
}

private fun String.shouldLogWireMessage(): Boolean {
    if (!contains("\"type\":\"event\"")) return true
    return contains("\"channel\":\"control_lease\"") ||
        contains("\"channel\":\"event\"")
}
