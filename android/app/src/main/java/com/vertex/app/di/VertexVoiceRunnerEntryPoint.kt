package com.vertex.app.di

import com.vertex.app.voice.VertexVoiceRunner
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

/**
 * Entry point for components that are not created by Hilt (e.g. VoiceInteractionSession,
 * WakeWordService) to obtain VertexVoiceRunner.
 */
@EntryPoint
@InstallIn(dagger.hilt.components.SingletonComponent::class)
interface VertexVoiceRunnerEntryPoint {
    fun vertexVoiceRunner(): VertexVoiceRunner
}
