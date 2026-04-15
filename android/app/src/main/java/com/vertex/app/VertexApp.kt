package com.vertex.app

import android.app.Application
import android.util.Log
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class VertexApp : Application() {

    override fun onCreate() {
        super.onCreate()
        Log.i("VertexApp", "Backend URL: ${BuildConfig.DEFAULT_BACKEND_URL}")
    }
}
