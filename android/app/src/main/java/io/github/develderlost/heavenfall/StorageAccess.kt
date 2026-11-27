package io.github.develderlost.heavenfall

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import java.io.File

/**
 * Storage access on Android 11 and newer. Two ways to the same files, used in this order:
 * "All files access" (MANAGE_EXTERNAL_STORAGE), which lets the app open the game and write the mod as plain files
 * (nothing is copied twice), and the system's picker (SAF), which works everywhere but only through content:// URIs.
 */
object StorageAccess {

    /** Whether the player allowed "All files access" to this app (Android 11 and newer; false before). */
    fun hasAllFiles(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && Environment.isExternalStorageManager()

    /** The settings page of this app's "All files access" switch. */
    fun appSettings(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:${context.packageName}"))

    /** The list of all apps' "All files access" switches, for phones that lack the page of one app. */
    fun allSettings(): Intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)

    /**
     * The real file or folder behind a picker's URI, when it is one of the device's own storage volumes (or a
     * Downloads path); null for the providers of other apps (Azahar's own folder provider, cloud drives...).
     */
    fun pathOf(uri: Uri): File? {
        val id = try {
            if (DocumentsContract.isTreeUri(uri)) {
                DocumentsContract.getTreeDocumentId(uri)
            } else {
                DocumentsContract.getDocumentId(uri)
            }
        } catch (e: Exception) {
            return null
        }
        return when (uri.authority) {
            "com.android.externalstorage.documents" -> {
                val volume = id.substringBefore(':')
                val relative = id.substringAfter(':', "")
                val base = if (volume == "primary") {
                    Environment.getExternalStorageDirectory()
                } else {
                    File("/storage/$volume")
                }
                if (relative.isEmpty()) base else File(base, relative)
            }
            "com.android.providers.downloads.documents" ->
                if (id.startsWith("raw:")) File(id.removePrefix("raw:")) else null
            else -> null
        }
    }

    /**
     * Whether `file` is inside another app's Android/data or Android/obb: since Android 11 even "All files access"
     * does not open those, so the picker (SAF) stays the way to them.
     */
    fun isRestricted(file: File): Boolean {
        val parts = file.absolutePath.split('/')
        val android = parts.indexOf("Android")
        return android >= 0 && android + 1 < parts.size && (parts[android + 1] == "data" || parts[android + 1] == "obb")
    }
}
