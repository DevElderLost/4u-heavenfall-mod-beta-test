package io.github.develderlost.heavenfall

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import io.github.develderlost.heavenfall.ui.HeavenfallApp
import io.github.develderlost.heavenfall.ui.HeavenfallTheme

class MainActivity : ComponentActivity() {
    private val model: InstallViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            HeavenfallTheme {
                HeavenfallApp(model)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        model.refreshStorage()      // "All files access" is switched in the system's settings, outside the app
    }
}
