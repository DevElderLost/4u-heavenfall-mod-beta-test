package io.github.develderlost.heavenfall

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import java.io.File
import java.io.IOException
import java.util.zip.ZipFile

/** Writes the mod into the emulator's folder, which the player chose with the system's folder picker. */
class ModFolder(private val context: Context) {

    /**
     * load/mods of the folder chosen, made when missing: the user folder of Azahar (what the program's own
     * core/install/targets.py mods_folder_for takes), its `load` folder or its `load/mods` folder.
     */
    fun modsDirectory(chosen: Uri): DocumentFile? {
        val root = DocumentFile.fromTreeUri(context, chosen) ?: return null
        return when (root.name?.lowercase()) {
            "mods" -> root
            "load" -> directory(root, "mods")
            else -> directory(root, "load")?.let { directory(it, "mods") }
        }
    }

    /** Whether `title`'s folder in `mods` holds files this program did not add (it has no settings_*.json of its own). */
    fun isForeign(mods: DocumentFile, title: String): Boolean {
        val existing = mods.findFile(title) ?: return false
        return existing.listFiles().none { it.name?.startsWith("settings_") == true }
    }

    /** The zip's `<title>/...` into `mods`/<title>, which is deleted first (old files left behind would still load). */
    fun install(zip: File, title: String, mods: DocumentFile, onFile: (Int) -> Unit) {
        mods.findFile(title)?.delete()
        val root = mods.createDirectory(title) ?: throw IOException("cannot create $title")
        val folders = HashMap<String, DocumentFile>()
        folders[""] = root
        var done = 0
        ZipFile(zip).use { archive ->
            for (entry in archive.entries()) {
                if (entry.isDirectory) {
                    continue
                }
                val parts = entry.name.substringAfter('/').split('/')
                var parent = root
                var path = ""
                for (name in parts.dropLast(1)) {
                    path = if (path.isEmpty()) name else "$path/$name"
                    val known = folders[path]
                    parent = known ?: (directory(parent, name) ?: throw IOException("cannot create $path"))
                    folders[path] = parent
                }
                val name = parts.last()
                val file = parent.createFile("application/octet-stream", name) ?: throw IOException("cannot create $name")
                if (file.name != name) {
                    file.renameTo(name)       // a provider may add an extension for the type: the mod needs its names
                }
                val output = context.contentResolver.openOutputStream(file.uri, "w") ?: throw IOException("cannot write $name")
                output.use { target -> archive.getInputStream(entry).use { it.copyTo(target, 1 shl 16) } }
                done += 1
                onFile(done)
            }
        }
    }

    /** `zip` as the file the player chose to save it to. */
    fun saveZip(zip: File, target: Uri) {
        val output = context.contentResolver.openOutputStream(target, "w") ?: throw IOException("cannot write $target")
        output.use { out -> zip.inputStream().use { it.copyTo(out, 1 shl 16) } }
    }

    private fun directory(parent: DocumentFile, name: String): DocumentFile? =
        parent.findFile(name)?.takeIf { it.isDirectory } ?: parent.createDirectory(name)
}
