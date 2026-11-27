package io.github.develderlost.heavenfall

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.documentfile.provider.DocumentFile
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.io.IOException
import java.util.Locale

data class GameState(val uri: Uri, val name: String, val check: CheckResult)

sealed interface Status {
    data object Idle : Status
    data class Working(val message: String) : Status
    data class Done(val message: String, val notices: List<String>) : Status
    data class Failed(val message: String) : Status
}

/** The two pages' state: the game, Azahar's folder, the options and the work in progress. */
class InstallViewModel(app: Application) : AndroidViewModel(app) {

    private val bridge = HeavenfallBridge(app)
    private val folder = ModFolder(app)
    private val preferences = app.getSharedPreferences("heavenfall", 0)
    // the languages of the program's own texts (the options, the game's problems)
    private val language = if (Locale.getDefault().language == "es") "es" else "en"

    var sections by mutableStateOf<List<SectionDef>>(emptyList())
        private set
    val values = mutableStateMapOf<String, Any>()

    var game by mutableStateOf<GameState?>(null)
        private set
    // the folder of an earlier run, unless its permission is gone (then it is chosen again)
    var destination by mutableStateOf<Uri?>(
        preferences.getString("destination", null)?.let(Uri::parse)?.takeIf { folder.usable(it) },
    )
        private set
    var destinationName by mutableStateOf<String?>(null)
        private set
    var status by mutableStateOf<Status>(Status.Working(app.getString(R.string.working_loading)))
        private set
    var confirmReplace by mutableStateOf(false)
        private set

    /** Whether "All files access" is on (Android 11 and newer): the game is read where it is, the mod written as files. */
    var allFiles by mutableStateOf(StorageAccess.hasAllFiles())
        private set

    val busy: Boolean get() = status is Status.Working

    /** Read the switch again: the player may have changed it in the system's settings. */
    fun refreshStorage() {
        allFiles = StorageAccess.hasAllFiles()
    }

    init {
        destination?.let { uri ->
            destinationName = runCatching { DocumentFile.fromTreeUri(app, uri)?.name }.getOrNull()
        }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val loaded = bridge.options(language)
                for (section in loaded) {
                    for (group in section.groups) {
                        for (option in group.options) {
                            values[option.field] = option.default
                        }
                    }
                }
                sections = loaded
                status = Status.Idle
            } catch (e: Throwable) {
                status = Status.Failed(describe(e))
            }
        }
    }

    private fun string(id: Int, vararg args: Any): String = getApplication<Application>().getString(id, *args)

    private fun describe(error: Throwable): String = error.message ?: error.javaClass.simpleName

    private fun displayName(uri: Uri): String {
        val resolver = getApplication<Application>().contentResolver
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                return cursor.getString(0) ?: uri.lastPathSegment ?: "game"
            }
        }
        return uri.lastPathSegment ?: "game"
    }

    fun pickGame(uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            status = Status.Working(string(R.string.working_checking))
            try {
                val name = displayName(uri)
                val result = bridge.openGame(uri) { status = Status.Working(string(R.string.working_copying)) }
                    .use { file -> bridge.check(file.path, language) }
                game = GameState(uri, name, result)
                status = Status.Idle
            } catch (e: Throwable) {
                game = null
                status = Status.Failed(describe(e))
            }
        }
    }

    fun pickDestination(uri: Uri) {
        try {
            getApplication<Application>().contentResolver.takePersistableUriPermission(
                uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (e: SecurityException) {
            // not persistable: the folder works for this run only
        }
        preferences.edit().putString("destination", uri.toString()).apply()
        destination = uri
        destinationName = runCatching { DocumentFile.fromTreeUri(getApplication(), uri)?.name }.getOrNull()
    }

    fun dismissReplace() {
        confirmReplace = false
    }

    private fun stageText(stage: String): String = when (stage) {
        "rom" -> string(R.string.stage_rom)
        "write" -> string(R.string.stage_write)
        "zip" -> string(R.string.stage_zip)
        else -> stage
    }

    /** The mod of the chosen game as cache/mod.zip; null (with the problem in `status`) when it cannot be made. */
    private fun buildMod(chosen: GameState): Pair<BuildResult, File>? {
        val zip = File(getApplication<Application>().cacheDir, "mod.zip")
        zip.delete()
        status = Status.Working(string(R.string.working_checking))
        val result = bridge.openGame(chosen.uri) { status = Status.Working(string(R.string.working_copying)) }
            .use { file ->
                bridge.build(file.path, zip, values.toMap(), language) { stage -> status = Status.Working(stageText(stage)) }
            }
        if (!result.ok) {
            zip.delete()
            status = Status.Failed(listOfNotNull(result.problem, result.detail).joinToString("\n\n").ifEmpty { string(R.string.err_generic) })
            return null
        }
        return result to zip
    }

    fun install(replaceConfirmed: Boolean = false) {
        val chosen = game ?: return
        val tree = destination ?: return
        confirmReplace = false
        viewModelScope.launch(Dispatchers.IO) {
            var zip: File? = null
            try {
                val title = chosen.check.title ?: throw IOException(string(R.string.err_generic))
                val mods = folder.target(tree) ?: throw IOException(string(R.string.err_destination))
                if (!replaceConfirmed && folder.isForeign(mods, title)) {
                    confirmReplace = true
                    return@launch
                }
                val (built, made) = buildMod(chosen) ?: return@launch
                zip = made
                status = Status.Working(string(R.string.stage_install, 0, built.files))
                folder.install(made, title, mods) { done ->
                    status = Status.Working(string(R.string.stage_install, done, built.files))
                }
                status = Status.Done(string(R.string.done_installed, title), built.notices)
            } catch (e: Throwable) {
                status = Status.Failed(describe(e))
            } finally {
                zip?.delete()
            }
        }
    }

    fun saveZip(target: Uri) {
        val chosen = game ?: return
        viewModelScope.launch(Dispatchers.IO) {
            var zip: File? = null
            try {
                val (built, made) = buildMod(chosen) ?: return@launch
                zip = made
                folder.saveZip(made, target)
                status = Status.Done(string(R.string.done_zip_saved), built.notices)
            } catch (e: Throwable) {
                status = Status.Failed(describe(e))
            } finally {
                zip?.delete()
            }
        }
    }
}
