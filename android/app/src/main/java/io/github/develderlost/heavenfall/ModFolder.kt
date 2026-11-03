package io.github.develderlost.heavenfall

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.documentfile.provider.DocumentFile
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.util.zip.CRC32
import java.util.zip.ZipEntry
import java.util.zip.ZipFile

/**
 * Writes the mod into the emulator's folder, which the player chose with the system's folder picker.
 *
 * With "All files access" (StorageAccess) the folder is written as plain files; without it, or for a folder that
 * Android keeps from plain files (another app's Android/data), through the picker's URI (SAF). Either way a file
 * the folder already has with the same content is left alone, so installing again copies only what changed.
 */
class ModFolder(private val context: Context) {

    /** `load/mods` of the folder chosen, in one of the two ways. */
    sealed interface Target {
        data class Direct(val mods: File) : Target
        data class Saf(val mods: DocumentFile, val tree: Uri) : Target
    }

    /** The folder chosen as a plain folder, when "All files access" allows it; null otherwise (no folder is made). */
    private fun directRoot(chosen: Uri): File? {
        if (!StorageAccess.hasAllFiles()) {
            return null
        }
        val root = StorageAccess.pathOf(chosen) ?: return null
        return root.takeIf { it.isDirectory && it.canWrite() && !StorageAccess.isRestricted(it) }
    }

    /** Whether the folder saved from an earlier run can still be written, so the app does not offer a dead one. */
    fun usable(chosen: Uri): Boolean {
        val persisted = context.contentResolver.persistedUriPermissions.any {
            it.uri == chosen && it.isReadPermission && it.isWritePermission
        }
        return persisted || directRoot(chosen) != null
    }

    /**
     * load/mods of the folder chosen, made when missing: the user folder of Azahar (what the program's own
     * core/install/targets.py mods_folder_for takes), its `load` folder or its `load/mods` folder.
     */
    fun target(chosen: Uri): Target? {
        directRoot(chosen)?.let { root ->
            val mods = when (root.name.lowercase()) {
                "mods" -> root
                "load" -> File(root, "mods")
                else -> File(root, "load/mods")
            }
            if ((mods.isDirectory || mods.mkdirs()) && mods.canWrite()) {
                return Target.Direct(mods)
            }
        }
        val root = DocumentFile.fromTreeUri(context, chosen) ?: return null
        val mods = when (root.name?.lowercase()) {
            "mods" -> root
            "load" -> directory(root, "mods")
            else -> directory(root, "load")?.let { directory(it, "mods") }
        } ?: return null
        return Target.Saf(mods, chosen)
    }

    /** Whether `title`'s folder in `mods` holds files this program did not add (it has no settings_*.json of its own). */
    fun isForeign(target: Target, title: String): Boolean = when (target) {
        is Target.Direct -> {
            val existing = File(target.mods, title)
            existing.isDirectory && (existing.list() ?: emptyArray()).none { it.startsWith("settings_") }
        }
        is Target.Saf -> {
            val existing = target.mods.findFile(title)
            existing != null && existing.listFiles().none { it.name?.startsWith("settings_") == true }
        }
    }

    /**
     * The zip's `<title>/...` into `mods`/<title>. Files that are already there with the same content are not
     * written again, and files the zip does not have are deleted (old files left behind would still load).
     */
    fun install(zip: File, title: String, target: Target, onFile: (Int) -> Unit) {
        when (target) {
            is Target.Direct -> installDirect(zip, title, target.mods, onFile)
            is Target.Saf -> SafWriter(target.tree).install(zip, title, target.mods.uri, onFile)
        }
    }

    /** `zip` as the file the player chose to save it to. */
    fun saveZip(zip: File, target: Uri) {
        val output = context.contentResolver.openOutputStream(target, "w") ?: throw IOException("cannot write $target")
        output.use { out -> zip.inputStream().use { it.copyTo(out, 1 shl 16) } }
    }

    private fun directory(parent: DocumentFile, name: String): DocumentFile? =
        parent.findFile(name)?.takeIf { it.isDirectory } ?: parent.createDirectory(name)

    /** The entry's path below the zip's `<title>/` folder. */
    private fun relativeName(entry: ZipEntry): String = entry.name.substringAfter('/')

    private fun crcOf(input: InputStream): Long {
        val crc = CRC32()
        val buffer = ByteArray(1 shl 16)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) {
                break
            }
            crc.update(buffer, 0, count)
        }
        return crc.value
    }

    private fun installDirect(zip: File, title: String, mods: File, onFile: (Int) -> Unit) {
        val root = File(mods, title)
        if (root.exists() && !root.isDirectory) {
            root.delete()
        }
        if (!root.isDirectory && !root.mkdirs()) {
            throw IOException("cannot create $title")
        }
        val base = root.canonicalPath + File.separator
        val keep = HashSet<String>()
        var done = 0
        ZipFile(zip).use { archive ->
            for (entry in archive.entries()) {
                if (entry.isDirectory) {
                    continue
                }
                val file = File(root, relativeName(entry))
                if (!file.canonicalPath.startsWith(base)) {
                    throw IOException("unsafe path in the mod: ${entry.name}")
                }
                keep.add(file.canonicalPath)
                val same = file.isFile && entry.crc >= 0 && file.length() == entry.size &&
                    file.inputStream().use { crcOf(it) } == entry.crc
                if (!same) {
                    if (file.isDirectory) {
                        file.deleteRecursively()
                    }
                    file.parentFile?.mkdirs()
                    archive.getInputStream(entry).use { input ->
                        file.outputStream().use { input.copyTo(it, 1 shl 16) }
                    }
                }
                done += 1
                onFile(done)
            }
        }
        prune(root, keep)
    }

    /** Deletes what is under `dir` and not in `keep`, and the folders that end up empty. */
    private fun prune(dir: File, keep: Set<String>) {
        for (child in dir.listFiles().orEmpty()) {
            if (child.isDirectory) {
                prune(child, keep)
                if (child.list().isNullOrEmpty()) {
                    child.delete()
                }
            } else if (child.canonicalPath !in keep) {
                child.delete()
            }
        }
    }

    /** The same work as installDirect through the picker's URIs, listing each folder once instead of asking per file. */
    private inner class SafWriter(private val tree: Uri) {

        private inner class Node(val uri: Uri, val isDir: Boolean, val size: Long)

        private val resolver = context.contentResolver
        private val listings = HashMap<Uri, MutableMap<String, Node>>()

        private fun listing(dir: Uri): MutableMap<String, Node> = listings.getOrPut(dir) {
            val result = HashMap<String, Node>()
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getDocumentId(dir))
            val columns = arrayOf(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE,
                DocumentsContract.Document.COLUMN_SIZE,
            )
            resolver.query(children, columns, null, null, null)?.use { cursor ->
                while (cursor.moveToNext()) {
                    val name = cursor.getString(1) ?: continue
                    val isDir = cursor.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR
                    val size = if (cursor.isNull(3)) -1L else cursor.getLong(3)
                    result[name] = Node(DocumentsContract.buildDocumentUriUsingTree(tree, cursor.getString(0)), isDir, size)
                }
            }
            result
        }

        private fun delete(uri: Uri) {
            DocumentsContract.deleteDocument(resolver, uri)
        }

        private fun subdirectory(parent: Uri, name: String): Uri {
            val list = listing(parent)
            val found = list[name]
            if (found != null && found.isDir) {
                return found.uri
            }
            if (found != null) {
                delete(found.uri)
            }
            val created = DocumentsContract.createDocument(resolver, parent, DocumentsContract.Document.MIME_TYPE_DIR, name)
                ?: throw IOException("cannot create $name")
            list[name] = Node(created, true, -1L)
            listings[created] = HashMap()
            return created
        }

        private fun displayName(uri: Uri): String? =
            resolver.query(uri, arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME), null, null, null)?.use {
                if (it.moveToFirst()) it.getString(0) else null
            }

        fun install(zip: File, title: String, mods: Uri, onFile: (Int) -> Unit) {
            val root = subdirectory(mods, title)
            val files = HashSet<String>()
            val folders = HashSet<String>()
            var done = 0
            ZipFile(zip).use { archive ->
                for (entry in archive.entries()) {
                    if (entry.isDirectory) {
                        continue
                    }
                    val parts = relativeName(entry).split('/')
                    var parent = root
                    var path = ""
                    for (name in parts.dropLast(1)) {
                        path = if (path.isEmpty()) name else "$path/$name"
                        folders.add(path)
                        parent = subdirectory(parent, name)
                    }
                    val name = parts.last()
                    files.add(if (path.isEmpty()) name else "$path/$name")
                    val list = listing(parent)
                    val existing = list[name]
                    val same = existing != null && !existing.isDir && entry.crc >= 0 && existing.size == entry.size &&
                        (resolver.openInputStream(existing.uri)?.use { crcOf(it) } ?: -1L) == entry.crc
                    if (!same) {
                        var target = existing?.takeIf { !it.isDir }?.uri
                        if (target == null) {
                            existing?.let { delete(it.uri) }
                            target = DocumentsContract.createDocument(resolver, parent, "application/octet-stream", name)
                                ?: throw IOException("cannot create $name")
                            if (displayName(target) != name) {
                                // a provider may add an extension for the type: the mod needs its names
                                target = DocumentsContract.renameDocument(resolver, target, name) ?: target
                            }
                        }
                        val output = resolver.openOutputStream(target, "wt") ?: throw IOException("cannot write $name")
                        output.use { out -> archive.getInputStream(entry).use { it.copyTo(out, 1 shl 16) } }
                        list[name] = Node(target, false, entry.size)
                    }
                    done += 1
                    onFile(done)
                }
            }
            prune(root, "", files, folders)
        }

        private fun prune(dir: Uri, relative: String, files: Set<String>, folders: Set<String>) {
            for ((name, node) in listing(dir).toMap()) {
                val path = if (relative.isEmpty()) name else "$relative/$name"
                if (node.isDir) {
                    if (path in folders) {
                        prune(node.uri, path, files, folders)
                    } else {
                        delete(node.uri)
                    }
                } else if (path !in files) {
                    delete(node.uri)
                }
            }
        }
    }
}
