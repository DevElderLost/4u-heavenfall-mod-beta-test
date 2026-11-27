package io.github.develderlost.heavenfall

import org.json.JSONArray
import org.json.JSONObject

// The Options page as core/app/web.py (options) describes it: sections, groups and options, in the app's language.

data class Choice(val value: String, val label: String, val help: String)

data class OptionDef(
    val field: String,
    val label: String,
    val help: String,
    val kind: String,               // "bool", "choice" or "number"
    val default: Any,               // Boolean, String (a choice's value) or Int
    val requires: String?,
    val alsoWith: String?,
    val choices: List<Choice>,
    val minimum: Int,
    val maximum: Int,
)

data class GroupDef(val title: String, val description: String, val options: List<OptionDef>)

data class SectionDef(val title: String, val groups: List<GroupDef>)

/** What core/app/web.py (check_game) says of a game file. */
data class CheckResult(val ok: Boolean, val title: String?, val region: String?, val problem: String?)

/** What core/app/web.py (build) says of a mod. */
data class BuildResult(
    val ok: Boolean,
    val title: String?,
    val files: Int,
    val notices: List<String>,
    val problem: String?,
    val detail: String?,
)

private fun JSONObject.text(key: String): String = if (isNull(key)) "" else optString(key, "")

private fun JSONObject.textOrNull(key: String): String? = if (isNull(key)) null else optString(key, "").ifEmpty { null }

private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

private fun parseOption(o: JSONObject): OptionDef {
    val kind = o.getString("kind")
    val default: Any = when (kind) {
        "bool" -> o.getBoolean("default")
        "number" -> o.getInt("default")
        else -> o.getString("default")
    }
    val choices = if (o.has("choices")) {
        o.getJSONArray("choices").objects().map { Choice(it.getString("value"), it.text("label"), it.text("help")) }
    } else {
        emptyList()
    }
    return OptionDef(
        field = o.getString("field"),
        label = o.text("label"),
        help = o.text("help"),
        kind = kind,
        default = default,
        requires = o.textOrNull("requires"),
        alsoWith = o.textOrNull("also_with"),
        choices = choices,
        minimum = if (o.has("minimum")) o.getInt("minimum") else 0,
        maximum = if (o.has("maximum")) o.getInt("maximum") else 0,
    )
}

fun parseSections(json: String): List<SectionDef> =
    JSONArray(json).objects().map { section ->
        SectionDef(
            section.text("title"),
            section.getJSONArray("groups").objects().map { group ->
                GroupDef(group.text("title"), group.text("description"), group.getJSONArray("options").objects().map(::parseOption))
            },
        )
    }

fun parseCheck(json: String): CheckResult {
    val o = JSONObject(json)
    return CheckResult(o.getBoolean("ok"), o.textOrNull("title"), o.textOrNull("region"), o.textOrNull("problem"))
}

fun parseBuild(json: String): BuildResult {
    val o = JSONObject(json)
    val notices = if (o.has("notices")) {
        o.getJSONArray("notices").let { array -> (0 until array.length()).map { array.getString(it) } }
    } else {
        emptyList()
    }
    return BuildResult(o.getBoolean("ok"), o.textOrNull("title"), o.optInt("files", 0), notices, o.textOrNull("problem"), o.textOrNull("detail"))
}

/** Whether `field` is on: a switch that is on, a number other than 0, a choice that is not its first one. */
fun isOn(field: String, values: Map<String, Any>, definitions: Map<String, OptionDef>): Boolean =
    when (val value = values[field]) {
        is Boolean -> value
        is Int -> value != 0
        is String -> value != definitions[field]?.choices?.firstOrNull()?.value
        else -> true
    }

/** The same rule as the program's Options page (core/gui/options.py, Option.requires and also_with). */
fun isEnabled(option: OptionDef, values: Map<String, Any>, definitions: Map<String, OptionDef>): Boolean {
    val requires = option.requires ?: return true
    val also = option.alsoWith
    return isOn(requires, values, definitions) || (also != null && isOn(also, values, definitions))
}
