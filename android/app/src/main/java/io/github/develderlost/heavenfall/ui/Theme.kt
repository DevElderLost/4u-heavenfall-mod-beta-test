package io.github.develderlost.heavenfall.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Gold = Color(0xFFE0B04A)
private val Navy = Color(0xFF1B2A41)

private val Dark = darkColorScheme(primary = Gold, onPrimary = Navy, secondary = Gold)
private val Light = lightColorScheme(primary = Navy, secondary = Gold)

@Composable
fun HeavenfallTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}
