package io.github.develderlost.heavenfall.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import io.github.develderlost.heavenfall.InstallViewModel
import io.github.develderlost.heavenfall.R

/** The two pages of the program (core/app/edition.py: install, options), with the system's pickers they need. */
@Composable
fun HeavenfallApp(model: InstallViewModel) {
    var page by rememberSaveable { mutableIntStateOf(0) }

    val pickGame = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            model.pickGame(uri)
        }
    }
    val pickDestination = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            model.pickDestination(uri)
        }
    }
    val saveZip = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        if (uri != null) {
            model.saveZip(uri)
        }
    }

    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = page == 0,
                    onClick = { page = 0 },
                    icon = { Icon(Icons.Filled.Home, contentDescription = null) },
                    label = { Text(stringResource(R.string.tab_install)) },
                )
                NavigationBarItem(
                    selected = page == 1,
                    onClick = { page = 1 },
                    icon = { Icon(Icons.Filled.Settings, contentDescription = null) },
                    label = { Text(stringResource(R.string.tab_options)) },
                )
            }
        },
    ) { padding ->
        if (page == 0) {
            InstallScreen(
                model = model,
                onPickGame = { pickGame.launch(arrayOf("*/*")) },
                onPickDestination = { pickDestination.launch(null) },
                onSaveZip = { saveZip.launch("Heavenfall-Beta.zip") },
                modifier = Modifier.padding(padding),
            )
        } else {
            OptionsScreen(model = model, modifier = Modifier.padding(padding))
        }
    }
}
