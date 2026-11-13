package io.github.develderlost.heavenfall.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import io.github.develderlost.heavenfall.InstallViewModel
import io.github.develderlost.heavenfall.OptionDef
import io.github.develderlost.heavenfall.isEnabled
import kotlin.math.roundToInt

/** The Options page: the program's own options (core/app/web.py, options), drawn from their description. */
@Composable
fun OptionsScreen(model: InstallViewModel, modifier: Modifier = Modifier) {
    val definitions = model.sections.flatMap { s -> s.groups.flatMap { it.options } }.associateBy { it.field }

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        for (section in model.sections) {
            Text(section.title, style = MaterialTheme.typography.headlineSmall)
            for (group in section.groups) {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (group.title.isNotEmpty()) {
                            Text(group.title, style = MaterialTheme.typography.titleMedium)
                        }
                        if (group.description.isNotEmpty()) {
                            Text(
                                group.description,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        for (option in group.options) {
                            OptionRow(option, model.values, isEnabled(option, model.values, definitions))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OptionRow(option: OptionDef, values: MutableMap<String, Any>, enabled: Boolean) {
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        when (option.kind) {
            "bool" -> Row(verticalAlignment = Alignment.CenterVertically) {
                Text(option.label, Modifier.weight(1f))
                Switch(
                    checked = values[option.field] as? Boolean ?: false,
                    onCheckedChange = { values[option.field] = it },
                    enabled = enabled,
                )
            }
            "number" -> {
                val current = values[option.field] as? Int ?: option.minimum
                Text("${option.label}: $current")
                Slider(
                    value = current.toFloat(),
                    onValueChange = { values[option.field] = it.roundToInt() },
                    valueRange = option.minimum.toFloat()..option.maximum.toFloat(),
                    steps = (option.maximum - option.minimum - 1).coerceAtLeast(0),
                    enabled = enabled,
                )
            }
            else -> {
                Text(option.label)
                for (choice in option.choices) {
                    val selected = values[option.field] == choice.value
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .selectable(
                                selected = selected,
                                enabled = enabled,
                                role = Role.RadioButton,
                                onClick = { values[option.field] = choice.value },
                            ),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = selected, onClick = null, enabled = enabled)
                        Text(choice.label, Modifier.padding(start = 8.dp))
                    }
                }
            }
        }
        if (option.help.isNotEmpty()) {
            Text(
                option.help,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
