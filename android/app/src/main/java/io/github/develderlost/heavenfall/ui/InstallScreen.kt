package io.github.develderlost.heavenfall.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.develderlost.heavenfall.InstallViewModel
import io.github.develderlost.heavenfall.R
import io.github.develderlost.heavenfall.Status

/** The Install page: the game, Azahar's folder, then Install (or a zip to extract by hand). */
@Composable
fun InstallScreen(
    model: InstallViewModel,
    onPickGame: () -> Unit,
    onPickDestination: () -> Unit,
    onSaveZip: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val game = model.game
    val status = model.status
    val gameOk = game?.check?.ok == true
    val idle = status !is Status.Working

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineMedium)
        Text(stringResource(R.string.tagline), style = MaterialTheme.typography.bodyMedium)
        Text(
            stringResource(R.string.privacy),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.game_title), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(R.string.game_help), style = MaterialTheme.typography.bodySmall)
                Button(onClick = onPickGame, enabled = idle) { Text(stringResource(R.string.choose_game)) }
                when {
                    game == null -> Text(stringResource(R.string.game_none))
                    gameOk -> Text(stringResource(R.string.game_ok, game.name, game.check.region ?: ""))
                    else -> Text(
                        "${game.name}: ${game.check.problem ?: ""}",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.dest_title), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(R.string.dest_help), style = MaterialTheme.typography.bodySmall)
                Button(onClick = onPickDestination, enabled = idle) { Text(stringResource(R.string.choose_dest)) }
                val name = model.destinationName
                Text(
                    if (model.destination == null) {
                        stringResource(R.string.dest_none)
                    } else {
                        stringResource(R.string.dest_chosen, name ?: model.destination.toString())
                    },
                )
            }
        }

        Button(
            onClick = { model.install() },
            enabled = idle && gameOk && model.destination != null,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.install)) }
        OutlinedButton(
            onClick = onSaveZip,
            enabled = idle && gameOk,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.save_zip)) }
        if (!(gameOk && model.destination != null)) {
            Text(
                stringResource(R.string.install_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        when (status) {
            is Status.Working -> {
                LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(status.message)
            }
            is Status.Done -> {
                Text(status.message)
                if (status.notices.isNotEmpty()) {
                    Text(stringResource(R.string.notices_title), style = MaterialTheme.typography.titleSmall)
                    status.notices.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
            is Status.Failed -> Text(status.message, color = MaterialTheme.colorScheme.error)
            Status.Idle -> Unit
        }
    }

    if (model.confirmReplace) {
        AlertDialog(
            onDismissRequest = { model.dismissReplace() },
            title = { Text(stringResource(R.string.replace_title)) },
            text = { Text(stringResource(R.string.replace_text)) },
            confirmButton = {
                TextButton(onClick = { model.install(replaceConfirmed = true) }) {
                    Text(stringResource(R.string.replace_yes))
                }
            },
            dismissButton = {
                TextButton(onClick = { model.dismissReplace() }) { Text(stringResource(R.string.replace_no)) }
            },
        )
    }
}
