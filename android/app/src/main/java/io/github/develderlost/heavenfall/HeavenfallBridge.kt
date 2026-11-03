package io.github.develderlost.heavenfall

import android.content.Context
import android.net.Uri
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.Closeable
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.util.zip.ZipInputStream

/** Told by Python (heavenfall_android.build) each time the mod's build starts a stage. */
class StageListener(private val callback: (String) -> Unit) {
    fun onStage(name: String) = callback(name)
}

/** A game file Python can open by `path`; close it when the work is done. */
class GameFile(val path: String, private val onClose: () -> Unit) : Closeable {
    override fun close() = onClose()
}

/**
 * The calls into the program's Python code (android/app/src/main/python/heavenfall_android.py, which goes to
 * core/app/web.py). None of them may run on the main thread.
 */
class HeavenfallBridge(private val context: Context) {

    private val module: PyObject by lazy {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
        val bridge = Python.getInstance().getModule("heavenfall_android")
        bridge.callAttr("attach", unpackCode().absolutePath)
        bridge
    }

    /** The `core` package, unpacked from the APK's assets the first time after each install or update. */
    private fun unpackCode(): File {
        val root = File(context.filesDir, "heavenfall-code")
        val stamp = context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime.toString()
        val marker = File(root, ".stamp")
        if (marker.isFile && marker.readText() == stamp) {
            return root
        }
        root.deleteRecursively()
        root.mkdirs()
        val base = root.canonicalPath + File.separator
        ZipInputStream(context.assets.open("heavenfall-core.zip").buffered()).use { zip ->
            var entry = zip.nextEntry
            while (entry != null) {
                val target = File(root, entry.name)
                if (!target.canonicalPath.startsWith(base)) {
                    throw IOException("unsafe path in the code bundle: ${entry.name}")
                }
                if (entry.isDirectory) {
                    target.mkdirs()
                } else {
                    target.parentFile?.mkdirs()
                    target.outputStream().use { zip.copyTo(it, 1 shl 16) }
                }
                zip.closeEntry()
                entry = zip.nextEntry
            }
        }
        marker.writeText(stamp)
        return root
    }

    fun options(language: String): List<SectionDef> =
        parseSections(module.callAttr("options", language).toString())

    fun check(path: String, language: String): CheckResult =
        parseCheck(module.callAttr("check", path, language).toString())

    fun build(
        path: String,
        zip: File,
        values: Map<String, Any>,
        language: String,
        onStage: (String) -> Unit,
    ): BuildResult {
        val personal = JSONObject()
        values.forEach { (field, value) -> personal.put(field, value) }
        val answer = module.callAttr(
            "build", path, zip.absolutePath, personal.toString(), language, StageListener(onStage),
        )
        return parseBuild(answer.toString())
    }

    /**
     * The chosen game as a path Python can read. The picker's file descriptor is reopened through /proc/self/fd when
     * it is a real, seekable file (no copy of a 1 GB game); otherwise the game is copied to the cache first.
     */
    fun openGame(uri: Uri, onCopy: () -> Unit = {}): GameFile {
        val resolver = context.contentResolver
        val descriptor = resolver.openFileDescriptor(uri, "r") ?: throw IOException("cannot open $uri")
        val direct = "/proc/self/fd/${descriptor.fd}"
        if (seekable(direct)) {
            return GameFile(direct) { descriptor.close() }
        }
        descriptor.close()
        onCopy()
        val copy = File(context.cacheDir, "game-copy")
        val input = resolver.openInputStream(uri) ?: throw IOException("cannot read $uri")
        input.use { source -> copy.outputStream().use { target -> source.copyTo(target, 1 shl 20) } }
        return GameFile(copy.absolutePath) { copy.delete() }
    }

    private fun seekable(path: String): Boolean =
        try {
            RandomAccessFile(path, "r").use {
                it.seek(1)
                it.read()
            }
            true
        } catch (e: Exception) {
            false
        }
}
