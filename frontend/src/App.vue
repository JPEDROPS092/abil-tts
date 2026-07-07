<template>
  <Toast position="bottom-right" />

  <div class="app-shell" @keydown="onGlobalKey">

    <!-- ── Topbar ─────────────────────────────────────────────────── -->
    <header class="topbar">
      <div class="topbar-brand">
        <img class="brand-logo" src="/abil.png" alt="Abil" />
        <div class="brand-text">
          <span class="brand-name">Abil</span>
          <span class="brand-badge">TTS</span>
        </div>
      </div>

      <div class="topbar-toolbar">
        <FileUpload
          mode="basic"
          name="file"
          choose-label="Abrir documento"
          accept=".txt,.md,.markdown,.docx,.pdf"
          custom-upload
          :auto="true"
          @uploader="uploadDocument"
          class="tb-upload"
        />
        <div class="tb-sep"></div>
        <Button icon="pi pi-clipboard" label="Colar" size="small" severity="secondary" text @click="pasteClipboard" />
        <Button icon="pi pi-times" label="Limpar" size="small" severity="danger" text @click="clearText" :disabled="!text.trim()" />
        <div class="tb-sep"></div>
        <Button
          icon="pi pi-bolt"
          :label="llmReviewing ? 'Revisando…' : 'Revisar com LLM'"
          size="small"
          severity="secondary"
          text
          @click="reviewTextWithLLM"
          :loading="llmReviewing"
          :disabled="!text.trim()"
        />
      </div>

      <div class="topbar-right">
        <div class="model-badge" :class="modelStatus.status">
          <span class="model-dot"></span>
          <span class="model-label">{{ modelStatusLabel }}</span>
        </div>
      </div>
    </header>

    <!-- ── Workspace ──────────────────────────────────────────────── -->
    <div class="workspace">

      <!-- Activity Bar -->
      <nav class="activity-bar">
        <button
          v-for="v in views"
          :key="v.id"
          class="nav-btn"
          :class="{ active: activeView === v.id }"
          @click="toggleView(v.id)"
          :title="v.label"
        >
          <div class="nav-icon-wrap">
            <i :class="['pi', v.icon]"></i>
            <span v-if="v.id === 'generate' && activeJobRunning" class="nav-badge pulse"></span>
            <span v-if="v.id === 'chat' && chatStreaming" class="nav-badge chat-badge"></span>
          </div>
          <span class="nav-label">{{ v.label }}</span>
        </button>
      </nav>

      <!-- Editor -->
      <main
        class="editor"
        :class="{ dropping: isDraggingOver }"
        @dragover.prevent="isDraggingOver = true"
        @dragleave.self="isDraggingOver = false"
        @drop.prevent="handleFileDrop"
      >
        <div v-if="!text" class="editor-empty">
          <div class="editor-empty-icon">
            <i class="pi pi-file-edit"></i>
          </div>
          <p class="editor-empty-title">Comece a escrever ou abra um documento</p>
          <p class="editor-empty-sub">Suporta TXT, MD, DOCX e PDF · Arraste um arquivo aqui</p>
          <div class="editor-empty-actions">
            <FileUpload
              mode="basic"
              name="file"
              choose-label="Abrir arquivo"
              accept=".txt,.md,.markdown,.docx,.pdf"
              custom-upload
              :auto="true"
              @uploader="uploadDocument"
              class="tb-upload-big"
            />
            <Button icon="pi pi-clipboard" label="Colar texto" severity="secondary" outlined @click="pasteClipboard" />
          </div>
        </div>

        <Textarea
          v-show="!!text || editorFocused"
          v-model="text"
          class="editor-ta"
          placeholder="Digite, cole ou arraste um documento aqui…"
          :auto-resize="false"
          @focus="editorFocused = true"
          @blur="editorFocused = false"
          @keydown.ctrl.enter.prevent="generateAudio()"
        />

        <div class="editor-foot" v-show="!!text">
          <div class="foot-left">
            <span class="foot-stat">{{ textStats }}</span>
            <span v-if="activeJobRunning" class="foot-job">
              <i class="pi pi-spin pi-cog"></i> {{ activeJob?.message || 'Gerando…' }}
            </span>
          </div>
          <span class="foot-hint">Ctrl+Enter para gerar · Selecione para diagrama parcial</span>
        </div>

        <div v-if="isDraggingOver" class="drop-overlay">
          <i class="pi pi-upload"></i>
          <span>Solte o arquivo para abrir</span>
        </div>
      </main>

      <!-- Side Panel -->
      <aside class="side-panel" :class="{ open: !!activeView }">
        <template v-if="activeView">
          <div class="panel-head">
            <span class="panel-title">
              <i :class="['pi', currentView?.icon]"></i>
              {{ currentView?.label }}
            </span>
            <button class="panel-close-btn" @click="activeView = null" title="Fechar (Esc)">
              <i class="pi pi-chevron-right"></i>
            </button>
          </div>

          <div class="panel-body">

            <!-- ─────────── GERAÇÃO ─────────────────────────────── -->
            <div v-show="activeView === 'generate'" class="pane">

              <!-- Voice & Model card -->
              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-microphone"></i>
                  <span>Voz e Modelo</span>
                </div>
                <div class="card-body">
                  <div class="fg-2">
                    <div class="field">
                      <label>Backend</label>
                      <Dropdown v-model="settings.backend" :options="meta.backends" option-label="label" option-value="id" @change="onModelChange" />
                    </div>
                    <div class="field">
                      <label>Device</label>
                      <Dropdown v-model="settings.device" :options="deviceOptions" option-label="label" option-value="value" @change="onModelChange" />
                    </div>
                    <div class="field">
                      <label>Voz / Speaker</label>
                      <Dropdown v-model="settings.speaker" :options="speakerOptions" />
                    </div>
                    <div class="field">
                      <label>Idioma</label>
                      <Dropdown v-model="settings.language" :options="meta.languages" />
                    </div>
                  </div>

                  <div class="speed-control">
                    <div class="speed-head">
                      <span class="speed-lbl"><i class="pi pi-gauge"></i> Velocidade</span>
                      <div class="speed-presets">
                        <button v-for="sp in [0.75, 1.0, 1.25, 1.5, 2.0]" :key="sp"
                          class="speed-preset" :class="{ active: Math.abs(generateOptions.speed - sp) < 0.01 }"
                          @click="generateOptions.speed = sp">{{ sp }}×</button>
                      </div>
                      <span class="speed-val">{{ generateOptions.speed.toFixed(2) }}×</span>
                    </div>
                    <Slider v-model="generateOptions.speed" :min="0.25" :max="3.0" :step="0.05" class="speed-slider" />
                    <span v-if="settings.backend !== 'edge'" class="f-hint">
                      <i class="pi pi-info-circle"></i> Suporte nativo apenas no Edge-TTS
                    </span>
                  </div>

                  <div class="toggle-stack">
                    <label class="tog">
                      <Checkbox v-model="settings.normalize_text" binary />
                      <span>Normalizar texto antes de gerar</span>
                    </label>
                    <label class="tog">
                      <Checkbox v-model="generateOptions.reviewBeforeTTS" binary />
                      <span>Revisar com LLM antes do TTS</span>
                      <span class="tog-badge">LLM</span>
                    </label>
                  </div>

                  <div class="btn-row mt-sm">
                    <Button label="Carregar modelo" severity="secondary" outlined size="small" icon="pi pi-download" @click="loadModel" />
                    <Button label="Salvar config" severity="secondary" outlined size="small" icon="pi pi-save" @click="saveSettings" />
                  </div>
                </div>
              </div>

              <!-- Generate card -->
              <div class="pane-card generate-card">
                <div class="card-head">
                  <i class="pi pi-play-circle"></i>
                  <span>Gerar Áudio</span>
                  <span class="card-head-hint">Ctrl+Enter</span>
                </div>
                <div class="card-body">
                  <Button
                    :icon="activeJobRunning ? 'pi pi-spin pi-spinner' : 'pi pi-play'"
                    :label="activeJobRunning ? `Gerando… ${activeJob?.progress || 0}%` : 'Gerar Áudio'"
                    :disabled="!canGenerate || activeJobRunning"
                    @click="generateAudio()"
                    class="generate-btn"
                  />
                  <Button
                    label="Pré-visualizar normalização"
                    severity="secondary"
                    outlined
                    class="full mt-sm"
                    size="small"
                    icon="pi pi-eye"
                    @click="previewNormalize"
                    :disabled="!text.trim()"
                  />

                  <div v-if="activeJob" class="job-card mt-sm">
                    <div class="jc-header">
                      <span class="status-dot" :class="activeJob.status"></span>
                      <span class="jc-msg">{{ activeJob.message || statusLabel(activeJob.status) }}</span>
                      <span v-if="activeJob.total_chunks > 0" class="jc-chunks">
                        {{ activeJob.current_chunk }}/{{ activeJob.total_chunks }}
                      </span>
                    </div>
                    <ProgressBar :value="activeJob.progress || 0" class="jc-bar" />
                    <Button
                      v-if="canCancel(activeJob)"
                      label="Cancelar"
                      size="small"
                      severity="danger"
                      text
                      icon="pi pi-stop"
                      class="mt-xs"
                      @click="cancelJob(activeJob.id)"
                    />
                  </div>

                  <div v-if="audioUrl" class="audio-card mt-sm">
                    <div class="audio-card-head">
                      <i class="pi pi-volume-up"></i>
                      <span>Áudio gerado</span>
                    </div>
                    <audio :src="audioUrl" controls class="audio-player" ref="audioPlayerEl" preload="metadata"></audio>
                    <Button
                      label="Baixar WAV"
                      icon="pi pi-download"
                      severity="secondary"
                      outlined
                      class="full mt-xs"
                      size="small"
                      @click="downloadAudio(activeJob?.id)"
                    />
                  </div>
                </div>
              </div>

              <!-- Jobs card -->
              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-list"></i>
                  <span>Histórico</span>
                  <button class="card-head-btn" @click="refreshJobs" title="Atualizar">
                    <i class="pi pi-refresh"></i>
                  </button>
                </div>
                <div class="card-body no-pad">
                  <div v-if="jobs.length === 0" class="card-empty">
                    <i class="pi pi-inbox"></i>
                    <span>Nenhum job ainda</span>
                  </div>
                  <div v-for="job in jobs.slice(0, 15)" :key="job.id" class="job-row" :class="job.status">
                    <div class="job-left">
                      <span class="status-dot sm" :class="job.status"></span>
                      <div class="job-info">
                        <code class="job-id">{{ job.id.slice(0, 8) }}</code>
                        <span class="job-meta-text">{{ job.backend }} · {{ job.input_words }} palavras</span>
                      </div>
                    </div>
                    <div class="job-right">
                      <span class="status-pill" :class="job.status">{{ statusLabel(job.status) }}</span>
                      <div class="job-acts">
                        <button class="icon-btn" :disabled="job.status !== 'done'" @click="playJob(job.id)" title="Ouvir">
                          <i class="pi pi-play"></i>
                        </button>
                        <button class="icon-btn warn" :disabled="!canCancel(job)" @click="cancelJob(job.id)" title="Cancelar">
                          <i class="pi pi-stop-circle"></i>
                        </button>
                        <button class="icon-btn danger" @click="deleteJob(job.id)" title="Remover">
                          <i class="pi pi-trash"></i>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

            </div><!-- /generate -->

            <!-- ─────────── CHAT ───────────────────────────────── -->
            <div v-show="activeView === 'chat'" class="pane chat-pane">
              <div class="chat-topbar">
                <div class="chat-quick-btns">
                  <button class="quick-btn" @click="chatQuickAction('resumir')" :disabled="!text.trim() || chatStreaming">
                    <i class="pi pi-align-left"></i> Resumir
                  </button>
                  <button class="quick-btn" @click="chatQuickAction('explicar')" :disabled="!text.trim() || chatStreaming">
                    <i class="pi pi-lightbulb"></i> Explicar
                  </button>
                  <button class="quick-btn" @click="chatQuickAction('pontos')" :disabled="!text.trim() || chatStreaming">
                    <i class="pi pi-list"></i> Pontos
                  </button>
                </div>
                <button class="icon-btn danger" @click="clearChat" title="Limpar conversa">
                  <i class="pi pi-trash"></i>
                </button>
              </div>

              <div class="chat-context-bar" v-if="text.trim()">
                <i class="pi pi-file-check"></i>
                <span>{{ docParagraphs.length }} parágrafos · {{ textStats }}</span>
              </div>
              <div class="chat-context-bar warn" v-else>
                <i class="pi pi-exclamation-triangle"></i>
                <span>Sem documento carregado — o chat não terá contexto</span>
              </div>

              <div class="chat-messages" ref="chatContainer">
                <div v-if="chatMessages.length === 0" class="chat-empty">
                  <i class="pi pi-comments"></i>
                  <p>Use as ações rápidas ou escreva uma mensagem.<br>O documento carregado será usado como contexto.</p>
                </div>

                <div v-for="(msg, i) in chatMessages" :key="i" class="chat-msg" :class="msg.role">
                  <div class="msg-avatar" :class="msg.role">
                    <i v-if="msg.role === 'assistant'" class="pi pi-bolt"></i>
                    <i v-else class="pi pi-user"></i>
                  </div>
                  <div class="msg-body">
                    <div class="msg-bubble" :class="msg.role">
                      <div
                        v-if="msg.role === 'assistant'"
                        class="msg-content markdown-body"
                        v-html="renderMarkdown(msg.content)"
                      ></div>
                      <p v-else class="msg-content">{{ msg.content }}</p>
                      <span v-if="chatStreaming && i === chatMessages.length - 1 && msg.role === 'assistant' && !msg.content" class="typing-dots">
                        <span></span><span></span><span></span>
                      </span>
                      <span v-if="chatStreaming && i === chatMessages.length - 1 && msg.role === 'assistant' && msg.content" class="stream-cursor">▋</span>
                    </div>
                    <div v-if="msg.role === 'assistant' && msg.content && !chatStreaming" class="msg-actions">
                      <button class="msg-act-btn" @click="copyText(msg.content)" title="Copiar texto">
                        <i class="pi pi-copy"></i> Copiar
                      </button>
                      <button class="msg-act-btn audio" @click="generateAudioFromMessage(msg.content)" title="Gerar áudio desta mensagem">
                        <i class="pi pi-volume-up"></i> Áudio
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="chat-input-area">
                <Textarea
                  v-model="chatInput"
                  class="chat-ta"
                  placeholder="Pergunte sobre o documento… (Enter para enviar, Shift+Enter nova linha)"
                  :auto-resize="true"
                  rows="2"
                  @keydown.enter.exact.prevent="sendChatMessage"
                />
                <Button
                  icon="pi pi-send"
                  :disabled="!chatInput.trim() || chatStreaming"
                  :loading="chatStreaming"
                  @click="sendChatMessage"
                  class="send-btn"
                />
              </div>
            </div><!-- /chat -->

            <!-- ─────────── DOCUMENTO ──────────────────────────── -->
            <div v-show="activeView === 'document'" class="pane doc-pane">
              <div class="doc-toolbar">
                <div class="doc-search-wrap">
                  <i class="pi pi-search doc-search-icon"></i>
                  <input
                    v-model="docSearch"
                    type="text"
                    class="doc-search-input"
                    placeholder="Buscar no documento…"
                    @keydown.escape="docSearch = ''"
                  />
                  <button v-if="docSearch" class="doc-search-clear" @click="docSearch = ''">
                    <i class="pi pi-times"></i>
                  </button>
                </div>
                <label class="tog small ml-auto">
                  <Checkbox v-model="docFollowTTS" binary />
                  <span>Acompanhar TTS</span>
                </label>
              </div>
              <div class="doc-stats-bar">
                <span>{{ filteredParagraphs.length }} / {{ docParagraphs.length }} parágrafos</span>
                <span v-if="docCurrentPara >= 0" class="doc-progress-txt">
                  Reproduzindo § {{ docCurrentPara + 1 }}
                </span>
              </div>

              <div class="doc-viewer" ref="docViewerEl">
                <div v-if="!text.trim()" class="doc-empty">
                  <i class="pi pi-file"></i>
                  <p>Carregue um documento para visualizar aqui.</p>
                </div>
                <div v-else-if="filteredParagraphs.length === 0" class="doc-empty">
                  <i class="pi pi-search"></i>
                  <p>Nenhum parágrafo encontrado para "{{ docSearch }}"</p>
                </div>
                <p
                  v-for="(para, idx) in filteredParagraphs"
                  :key="para.originalIdx"
                  :data-idx="para.originalIdx"
                  class="doc-p"
                  :class="{
                    active: para.originalIdx === docCurrentPara,
                    highlighted: para.hasMatch && docSearch
                  }"
                  @click="jumpToParaInEditor(para.originalIdx)"
                >
                  <span class="doc-para-num">{{ para.originalIdx + 1 }}</span>
                  <span v-if="para.hasMatch && docSearch" v-html="para.html"></span>
                  <span v-else>{{ para.text }}</span>
                </p>
              </div>
            </div><!-- /document -->

            <!-- ─────────── LLM ───────────────────────────────── -->
            <div v-show="activeView === 'llm'" class="pane">

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-server"></i>
                  <span>Provedor LLM</span>
                  <span class="conn-status" :class="connStatusClass">{{ connStatusText }}</span>
                </div>
                <div class="card-body">
                  <div class="preset-tabs">
                    <button
                      v-for="p in llmProviderPresets"
                      :key="p.value"
                      class="preset-tab"
                      :class="{ active: llmProviderPreset === p.value }"
                      @click="onLLMPresetChange({ value: p.value })"
                    >{{ p.label }}</button>
                  </div>

                  <div class="field mt-sm">
                    <label>Base URL</label>
                    <InputText v-model="llmConfig.base_url" class="full" placeholder="https://api.openai.com/v1" />
                  </div>
                  <div class="field mt-xs">
                    <label>API Key</label>
                    <Password v-model="llmConfig.api_key" :feedback="false" toggle-mask class="full" placeholder="sk-… ou bearer token" />
                  </div>

                  <div class="btn-row mt-sm">
                    <Button label="Salvar" icon="pi pi-save" @click="saveLLMConfig" size="small" />
                    <Button label="Testar" icon="pi pi-wifi" severity="secondary" outlined @click="testLLMConnection" :loading="llmTesting" size="small" />
                  </div>

                  <div v-if="llmTestResult" class="test-result mt-sm" :class="llmTestResult.success ? 'ok' : 'fail'">
                    <i :class="llmTestResult.success ? 'pi pi-check-circle' : 'pi pi-times-circle'"></i>
                    {{ llmTestResult.message }}
                  </div>
                </div>
              </div>

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-microchip"></i>
                  <span>Modelo</span>
                </div>
                <div class="card-body">
                  <div class="model-list">
                    <div
                      v-for="m in llmModelOptions"
                      :key="m.id"
                      class="model-card"
                      :class="{ selected: llmConfig.model === m.id }"
                      @click="llmConfig.model = m.id"
                    >
                      <div class="mc-top">
                        <span class="mc-brand" :class="m.brand.toLowerCase().replace(' ', '-')">{{ m.brand }}</span>
                        <span class="mc-id">{{ m.id }}</span>
                      </div>
                      <div class="mc-caps">
                        <span v-for="cap in m.capabilities" :key="cap" class="mc-cap">{{ cap }}</span>
                        <span v-if="m.supports_vision" class="mc-cap vision">👁 Vision</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-sparkles"></i>
                  <span>Ações do Documento</span>
                </div>
                <div class="card-body">
                  <div class="action-grid">
                    <button class="action-tile" @click="summarizeDocument" :disabled="!text.trim() || llmSummarizing" :class="{ loading: llmSummarizing }">
                      <i class="pi pi-align-left"></i>
                      <span>Resumir</span>
                    </button>
                    <button class="action-tile" @click="explainDocument" :disabled="!text.trim() || llmExplaining" :class="{ loading: llmExplaining }">
                      <i class="pi pi-lightbulb"></i>
                      <span>Explicar</span>
                    </button>
                  </div>

                  <div v-if="llmResult" class="llm-result mt-sm">
                    <div class="llm-result-head">
                      <span class="llm-result-label">{{ llmResultLabel }}</span>
                      <div class="llm-result-acts">
                        <button class="icon-btn" @click="copyLLMResult" title="Copiar"><i class="pi pi-copy"></i></button>
                        <button class="icon-btn" @click="generateAudioFromLLMResult" title="Gerar áudio"><i class="pi pi-volume-up"></i></button>
                      </div>
                    </div>
                    <div class="llm-result-text markdown-body" v-html="renderMarkdown(llmResult)"></div>
                  </div>
                </div>
              </div>

            </div><!-- /llm -->

            <!-- ─────────── DIAGRAMA ───────────────────────────── -->
            <div v-show="activeView === 'diagram'" class="pane">
              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-sitemap"></i>
                  <span>Mermaid Flowchart</span>
                </div>
                <div class="card-body">
                  <div class="fg-2">
                    <div class="field">
                      <label>Título</label>
                      <InputText v-model="settings.diagram_title" />
                    </div>
                    <div class="field">
                      <label>Escopo</label>
                      <Dropdown v-model="settings.diagram_scope" :options="diagramScopes" option-label="label" option-value="value" />
                    </div>
                  </div>

                  <Button
                    label="Gerar Diagrama"
                    icon="pi pi-sitemap"
                    class="full mt-sm"
                    @click="generateDiagram"
                    :disabled="!text.trim()"
                    :loading="diagramLoading"
                  />

                  <template v-if="diagramSource">
                    <div class="diag-source-wrap mt-sm">
                      <div class="diag-source-head">
                        <span>Código Mermaid</span>
                        <button class="icon-btn" @click="copyText(diagramSource)" title="Copiar"><i class="pi pi-copy"></i></button>
                      </div>
                      <pre class="diag-src">{{ diagramSource }}</pre>
                    </div>
                    <div v-if="diagramSvg" class="diag-preview" v-html="diagramSvg"></div>
                    <Button label="Baixar .mmd" icon="pi pi-download" severity="secondary" outlined class="full mt-sm" size="small" @click="downloadDiagram" />
                  </template>
                </div>
              </div>
            </div><!-- /diagram -->

            <!-- ─────────── MODELOS ───────────────────────────── -->
            <div v-show="activeView === 'models'" class="pane">

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-box"></i>
                  <span>Qwen3 TTS</span>
                  <span class="backend-tag local">Local</span>
                </div>
                <div class="card-body">
                  <div class="field">
                    <label>Model ID (HuggingFace)</label>
                    <InputText v-model="settings.qwen_model_id" class="full" placeholder="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" />
                  </div>
                </div>
              </div>

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-box"></i>
                  <span>Piper TTS</span>
                  <span class="backend-tag local">Local</span>
                </div>
                <div class="card-body">
                  <div class="fg">
                    <div class="field">
                      <label>Modelo (.onnx)</label>
                      <InputText v-model="settings.piper_model" class="full" placeholder="models/piper/model.onnx" />
                    </div>
                    <div class="field">
                      <label>Config (.json)</label>
                      <InputText v-model="settings.piper_config" class="full" placeholder="models/piper/model.onnx.json" />
                    </div>
                    <div class="field">
                      <label>Args extras</label>
                      <InputText v-model="settings.piper_args" class="full" placeholder="--noise-scale 0.667" />
                    </div>
                  </div>
                </div>
              </div>

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-box"></i>
                  <span>Coqui TTS</span>
                  <span class="backend-tag local">Local</span>
                </div>
                <div class="card-body">
                  <div class="field">
                    <label>Modelo</label>
                    <InputText v-model="settings.coqui_model" class="full" placeholder="tts_models/en/ljspeech/tacotron2-DDC" />
                  </div>
                </div>
              </div>

              <div class="pane-card">
                <div class="card-head">
                  <i class="pi pi-cloud"></i>
                  <span>Google Gemini TTS</span>
                  <span class="backend-tag cloud">Cloud</span>
                </div>
                <div class="card-body">
                  <div class="field">
                    <label>API Key (GEMINI_API_KEY)</label>
                    <Password v-model="settings.gemini_api_key" :feedback="false" toggle-mask class="full" placeholder="AIza…" />
                  </div>
                  <p class="f-hint mt-xs"><i class="pi pi-info-circle"></i> Usa o modelo gemini-3.1-flash-tts-preview via streaming</p>
                </div>
              </div>

              <div class="pane-card">
                <div class="card-body">
                  <Button label="Salvar e Recarregar Modelo" icon="pi pi-refresh" class="full" @click="saveSettingsAndLoad" />
                </div>
              </div>

            </div><!-- /models -->

          </div><!-- /panel-body -->
        </template>
      </aside>

    </div><!-- /workspace -->

    <!-- ── Status Bar ─────────────────────────────────────────────── -->
    <footer class="statusbar">
      <div class="sb-left">
        <span class="sb-item">
          <span class="sb-dot" :class="modelStatus.status"></span>
          <span class="sb-backend">{{ settings.backend || 'edge' }}</span>
        </span>
        <span v-if="settings.device" class="sb-item sb-dim">{{ settings.device }}</span>
        <span v-if="llmConfig.model" class="sb-item sb-dim">
          <i class="pi pi-bolt" style="font-size:9px"></i> {{ llmConfig.model }}
        </span>
      </div>
      <div class="sb-center">
        <span v-if="activeJobRunning" class="sb-item sb-warn">
          <i class="pi pi-spin pi-cog"></i>
          Gerando… {{ activeJob?.progress || 0 }}%
        </span>
        <span v-if="chatStreaming" class="sb-item sb-info">
          <i class="pi pi-spin pi-spinner"></i> LLM respondendo…
        </span>
      </div>
      <div class="sb-right">
        <span class="sb-item sb-dim">{{ textStats }}</span>
      </div>
    </footer>

  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useToast } from 'primevue/usetoast';
import { marked } from 'marked';
import mermaid from 'mermaid';

const toast = useToast();

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
  if (!text) return '';
  return marked.parse(text);
}

// ── Navigation ─────────────────────────────────────────────────────────────
const views = [
  { id: 'generate', label: 'Geração',   icon: 'pi-play-circle' },
  { id: 'chat',     label: 'Chat',      icon: 'pi-comments'    },
  { id: 'document', label: 'Documento', icon: 'pi-file'        },
  { id: 'llm',      label: 'LLM',       icon: 'pi-bolt'        },
  { id: 'diagram',  label: 'Diagrama',  icon: 'pi-sitemap'     },
  { id: 'models',   label: 'Modelos',   icon: 'pi-sliders-h'   },
];
const activeView = ref('generate');
const currentView = computed(() => views.find(v => v.id === activeView.value));

function toggleView(id) {
  activeView.value = activeView.value === id ? null : id;
}

// Keyboard shortcut: Escape → close panel
function onGlobalKey(event) {
  if (event.key === 'Escape' && activeView.value) {
    activeView.value = null;
  }
}

// ── Drag & Drop ────────────────────────────────────────────────────────────
const isDraggingOver = ref(false);
const editorFocused = ref(false);

async function handleFileDrop(event) {
  isDraggingOver.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const result = await api('/api/upload', { method: 'POST', body: form });
    text.value = result.text;
    notify('Documento carregado', file.name);
  } catch (error) {
    notify('Falha ao abrir documento', error.message, 'error');
  }
}

// ── Core state ─────────────────────────────────────────────────────────────
const text = ref('');
const meta = reactive({
  backends: [],
  speakers: [],
  edge_voices: [],
  languages: [],
  default_backend: 'edge',
  default_device: 'cpu',
});
const settings = reactive({
  backend: 'edge',
  device: 'cpu',
  speaker: 'Ryan',
  language: 'English',
  normalize_text: true,
  diagram_scope: 'auto',
  diagram_title: 'Text Flow',
  qwen_model_id: '',
  piper_model: '',
  piper_config: '',
  piper_args: '',
  coqui_model: '',
  gemini_api_key: '',
});
const generateOptions = reactive({
  speed: 1.0,
  reviewBeforeTTS: false,
});
const modelStatus = reactive({ status: 'idle', message: '' });
const jobs = ref([]);
const activeTaskId = ref(null);
const audioUrl = ref('');
const audioPlayerEl = ref(null);
const diagramSource = ref('');
const diagramSvg = ref('');
const diagramLoading = ref(false);
let taskTimer = null;
let modelTimer = null;

// ── LLM state ──────────────────────────────────────────────────────────────
const llmConfig = reactive({
  api_key: '',
  base_url: 'https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1',
  model: 'qwen3.6-flash',
});
const llmProviderPreset = ref('maas');
const llmProviderPresets = [
  { label: 'MaaS',   value: 'maas'   },
  { label: 'OpenAI', value: 'openai' },
  { label: 'Custom', value: 'custom' },
];
const llmModelOptions = ref([]);
const llmTesting = ref(false);
const llmTestResult = ref(null);
const llmConnected = ref(false);
const llmReviewing = ref(false);
const llmSummarizing = ref(false);
const llmExplaining = ref(false);
const llmResult = ref('');
const llmResultLabel = ref('');

// ── Chat state ─────────────────────────────────────────────────────────────
const chatMessages = ref([]);
const chatInput = ref('');
const chatStreaming = ref(false);
const chatContainer = ref(null);

// ── Document viewer state ──────────────────────────────────────────────────
const docFollowTTS = ref(true);
const docCurrentPara = ref(-1);
const docViewerEl = ref(null);
const docSearch = ref('');

// ── Computed ───────────────────────────────────────────────────────────────
const deviceOptions = [
  { label: 'cuda:0', value: 'cuda:0' },
  { label: 'cuda:1', value: 'cuda:1' },
  { label: 'cpu',    value: 'cpu'    },
];
const diagramScopes = [
  { label: 'Seleção se existir', value: 'auto'      },
  { label: 'Somente seleção',    value: 'selection' },
  { label: 'Texto completo',     value: 'full'      },
];
const speakerOptions = computed(() =>
  settings.backend === 'edge' ? meta.edge_voices : meta.speakers
);
const textStats = computed(() => {
  if (!text.value.trim()) return '0 caracteres';
  const words = text.value.trim().split(/\s+/).length;
  return `${text.value.length.toLocaleString()} chars · ${words.toLocaleString()} palavras`;
});
const modelStatusLabel = computed(() => ({
  idle:    'Aguardando',
  loading: 'Carregando…',
  ready:   'Pronto',
  error:   modelStatus.message || 'Erro',
}[modelStatus.status] || modelStatus.status));

const activeJob = computed(() => jobs.value.find(j => j.id === activeTaskId.value));
const activeJobRunning = computed(() =>
  activeJob.value && ['queued', 'processing'].includes(activeJob.value.status)
);
const canGenerate = computed(() =>
  text.value.trim().length > 0 && modelStatus.status === 'ready'
);
const docParagraphs = computed(() => {
  if (!text.value.trim()) return [];
  return text.value
    .split(/\n{2,}/)
    .map(p => p.replace(/\n/g, ' ').trim())
    .filter(Boolean);
});

const filteredParagraphs = computed(() => {
  const q = docSearch.value.trim().toLowerCase();
  return docParagraphs.value.map((text, originalIdx) => {
    if (!q) return { text, originalIdx, hasMatch: false, html: text };
    const hasMatch = text.toLowerCase().includes(q);
    if (!hasMatch) return null;
    const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const html = text.replace(new RegExp(escaped, 'gi'), match => `<mark>${match}</mark>`);
    return { text, originalIdx, hasMatch: true, html };
  }).filter(Boolean);
});

const connStatusClass = computed(() => {
  if (!llmConfig.api_key) return 'not-configured';
  if (llmTestResult.value?.success) return 'connected';
  if (llmTestResult.value?.success === false) return 'error';
  return 'unknown';
});

const connStatusText = computed(() => ({
  'connected':      '● Conectado',
  'error':          '● Erro',
  'not-configured': '○ Sem API Key',
  'unknown':        '○ Não testado',
}[connStatusClass.value] || ''));

// ── Watch active job for doc highlighting ──────────────────────────────────
watch(activeJob, job => {
  if (!job || !docFollowTTS.value) return;
  if (['done', 'cancelled', 'error'].includes(job.status)) {
    docCurrentPara.value = -1;
    return;
  }
  const total = docParagraphs.value.length;
  if (total === 0) return;
  const idx = Math.min(Math.floor(((job.progress || 0) / 100) * total), total - 1);
  if (idx !== docCurrentPara.value) {
    docCurrentPara.value = idx;
    nextTick(() => {
      const el = docViewerEl.value?.querySelector(`[data-idx="${idx}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }
});

// ── Helpers ────────────────────────────────────────────────────────────────
function notify(summary, detail = '', severity = 'info') {
  toast.add({ severity, summary, detail, life: 3200 });
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const ct = response.headers.get('content-type') || '';
  const payload = ct.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === 'object' ? payload.detail || payload.error : payload;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return payload;
}

function copyText(t) {
  navigator.clipboard.writeText(t).then(() => notify('Copiado!'));
}

function jumpToParaInEditor(idx) {
  // Switch to editor focus and try to scroll to paragraph
  const paras = text.value.split(/\n{2,}/);
  if (idx >= paras.length) return;
  const before = paras.slice(0, idx).join('\n\n');
  const ta = document.querySelector('.editor-ta');
  if (ta) {
    ta.focus();
    ta.setSelectionRange(before.length, before.length + paras[idx].length);
  }
}

// ── Meta / Settings ────────────────────────────────────────────────────────
async function loadMeta() {
  Object.assign(meta, await api('/api/meta'));
}

async function loadSettings() {
  Object.assign(settings, await api('/api/settings'));
  if (!speakerOptions.value.includes(settings.speaker)) {
    settings.speaker = speakerOptions.value[0] || 'Ryan';
  }
}

async function saveSettings() {
  const saved = await api('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  Object.assign(settings, saved);
  notify('Configuração salva');
}

async function saveSettingsAndLoad() {
  await saveSettings();
  await loadModel();
}

// ── Model loading ──────────────────────────────────────────────────────────
async function loadModel() {
  try {
    modelStatus.status = 'loading';
    modelStatus.message = '';
    await api('/api/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backend: settings.backend, device: settings.device }),
    });
    pollModel();
  } catch (error) {
    modelStatus.status = 'error';
    modelStatus.message = error.message;
    notify('Erro ao carregar modelo', error.message, 'error');
  }
}

async function pollModel() {
  clearTimeout(modelTimer);
  try {
    const status = await api(`/api/status?backend=${encodeURIComponent(settings.backend)}`);
    modelStatus.status = status.status;
    modelStatus.message = status.message || '';
    if (status.model_ready || status.status === 'ready') { modelStatus.status = 'ready'; return; }
    if (status.status === 'error') { notify('Erro ao carregar modelo', status.message, 'error'); return; }
  } catch (error) {
    modelStatus.status = 'error';
    modelStatus.message = error.message;
  }
  modelTimer = setTimeout(pollModel, 1500);
}

async function onModelChange() {
  if (!speakerOptions.value.includes(settings.speaker)) {
    settings.speaker = speakerOptions.value[0] || 'Ryan';
  }
  await saveSettings();
  await loadModel();
}

// ── Document upload ────────────────────────────────────────────────────────
async function uploadDocument(event) {
  const file = event.files?.[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const result = await api('/api/upload', { method: 'POST', body: form });
    text.value = result.text;
    notify('Documento carregado', file.name);
    activeView.value = 'document';
  } catch (error) {
    notify('Falha ao abrir documento', error.message, 'error');
  }
}

async function pasteClipboard() {
  try {
    const pasted = await navigator.clipboard.readText();
    text.value += pasted;
    notify('Texto colado', `${pasted.length} caracteres`);
  } catch {
    notify('Clipboard indisponível', 'Não foi possível ler a área de transferência.', 'warn');
  }
}

function clearText() {
  text.value = '';
  audioUrl.value = '';
  docCurrentPara.value = -1;
  diagramSource.value = '';
  diagramSvg.value = '';
}

// ── TTS generation ─────────────────────────────────────────────────────────
async function previewNormalize() {
  if (!text.value.trim()) return;
  try {
    const result = await api('/api/normalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value, language: settings.language }),
    });
    text.value = result.text;
    notify('Texto normalizado');
  } catch (error) {
    notify('Falha na normalização', error.message, 'error');
  }
}

async function generateAudio(customText = null) {
  const inputText = customText || text.value;
  if (!inputText.trim()) { notify('Texto vazio', 'Informe um texto.', 'warn'); return; }
  try {
    audioUrl.value = '';
    if (!customText) await saveSettings();
    const result = await api('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: inputText,
        backend: settings.backend,
        device: settings.device,
        speaker: settings.speaker,
        language: settings.language,
        normalize_text: settings.normalize_text,
        speed: generateOptions.speed,
        review_before_tts: generateOptions.reviewBeforeTTS,
      }),
    });
    activeTaskId.value = result.task_id;
    await refreshJobs();
    pollTask();
    if (activeView.value !== 'generate') activeView.value = 'generate';
  } catch (error) {
    notify('Falha ao iniciar geração', error.message, 'error');
  }
}

async function pollTask() {
  clearTimeout(taskTimer);
  if (!activeTaskId.value) return;
  try {
    const job = await api(`/api/task/${activeTaskId.value}`);
    await refreshJobs();
    if (['queued', 'processing'].includes(job.status)) {
      taskTimer = setTimeout(pollTask, 900);
    } else if (job.status === 'done') {
      playJob(job.id);
      notify('✓ Áudio pronto!', '', 'success');
    } else if (job.status === 'cancelled') {
      notify('Job cancelado');
    } else {
      notify('Geração falhou', job.message || job.error || '', 'error');
    }
  } catch {
    taskTimer = setTimeout(pollTask, 1200);
  }
}

async function refreshJobs() {
  const result = await api('/api/jobs?limit=80');
  jobs.value = result.jobs || [];
}

function canCancel(job) { return ['queued', 'processing'].includes(job.status); }

async function cancelJob(id) {
  await api(`/api/jobs/${id}/cancel`, { method: 'POST' });
  await refreshJobs();
}

async function deleteJob(id) {
  await api(`/api/jobs/${id}`, { method: 'DELETE' });
  if (activeTaskId.value === id) { activeTaskId.value = null; audioUrl.value = ''; }
  await refreshJobs();
}

function playJob(id) {
  activeTaskId.value = id;
  audioUrl.value = `/api/audio/${id}`;
}

function downloadAudio(id) {
  if (!id) return;
  const a = document.createElement('a');
  a.href = `/api/audio/${id}`;
  a.download = `abil-${id}.wav`;
  a.click();
}

// ── Diagram ────────────────────────────────────────────────────────────────
function selectedText() {
  const ta = document.querySelector('.editor-ta');
  if (!ta) return '';
  const { selectionStart: s = 0, selectionEnd: e = 0 } = ta;
  return e > s ? text.value.slice(s, e).trim() : '';
}

async function generateDiagram() {
  if (!text.value.trim()) return;
  diagramLoading.value = true;
  try {
    const result = await api('/api/diagram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text.value,
        selected_text: selectedText(),
        scope: settings.diagram_scope,
        title: settings.diagram_title,
        max_nodes: 12,
      }),
    });
    diagramSource.value = result.mermaid;
    const rendered = await mermaid.render(`diagram-${Date.now()}`, diagramSource.value);
    diagramSvg.value = rendered.svg;
    notify('Diagrama gerado');
  } catch (error) {
    notify('Falha no diagrama', error.message, 'error');
  } finally {
    diagramLoading.value = false;
  }
}

function downloadDiagram() {
  if (!diagramSource.value) return;
  const blob = new Blob([diagramSource.value], { type: 'text/plain;charset=utf-8' });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'diagram.mmd' });
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── LLM Config ─────────────────────────────────────────────────────────────
async function loadLLMConfig() {
  try {
    const cfg = await api('/api/llm/config');
    Object.assign(llmConfig, cfg);
    const models = await api('/api/llm/models');
    llmModelOptions.value = models.models || [];
  } catch (e) {
    console.warn('Could not load LLM config:', e);
  }
}

async function saveLLMConfig() {
  try {
    await api('/api/llm/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmConfig),
    });
    notify('Config LLM salva');
  } catch (error) {
    notify('Falha ao salvar config LLM', error.message, 'error');
  }
}

async function testLLMConnection() {
  llmTesting.value = true;
  llmTestResult.value = null;
  try {
    await saveLLMConfig();
    const result = await api('/api/llm/test', { method: 'POST' });
    llmTestResult.value = result;
    llmConnected.value = result.success;
    notify(result.success ? '✓ Conexão OK' : 'Falha na conexão', result.message, result.success ? 'success' : 'error');
  } catch (error) {
    llmTestResult.value = { success: false, message: error.message };
    llmConnected.value = false;
    notify('Erro de conexão', error.message, 'error');
  } finally {
    llmTesting.value = false;
  }
}

function onLLMPresetChange(e) {
  const preset = e.value;
  llmProviderPreset.value = preset;
  if (preset === 'maas') llmConfig.base_url = 'https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1';
  else if (preset === 'openai') llmConfig.base_url = 'https://api.openai.com/v1';
}

// ── LLM Quick Actions ──────────────────────────────────────────────────────
async function reviewTextWithLLM() {
  if (!text.value.trim()) return;
  llmReviewing.value = true;
  try {
    const result = await api('/api/llm/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value }),
    });
    text.value = result.text;
    notify('✓ Texto revisado pelo LLM', '', 'success');
  } catch (error) {
    notify('Falha na revisão LLM', error.message, 'error');
  } finally {
    llmReviewing.value = false;
  }
}

async function summarizeDocument() {
  if (!text.value.trim()) return;
  llmSummarizing.value = true;
  llmResult.value = '';
  try {
    const result = await api('/api/llm/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value }),
    });
    llmResult.value = result.text;
    llmResultLabel.value = 'Resumo do Documento';
    notify('Resumo gerado', '', 'success');
  } catch (error) {
    notify('Falha no resumo', error.message, 'error');
  } finally {
    llmSummarizing.value = false;
  }
}

async function explainDocument() {
  if (!text.value.trim()) return;
  llmExplaining.value = true;
  llmResult.value = '';
  try {
    const result = await api('/api/llm/explain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value }),
    });
    llmResult.value = result.text;
    llmResultLabel.value = 'Explicação do Documento';
    notify('Explicação gerada', '', 'success');
  } catch (error) {
    notify('Falha na explicação', error.message, 'error');
  } finally {
    llmExplaining.value = false;
  }
}

function copyLLMResult() { copyText(llmResult.value); }
async function generateAudioFromLLMResult() {
  if (!llmResult.value.trim()) return;
  await generateAudio(llmResult.value);
}

// ── Chat ────────────────────────────────────────────────────────────────────
function clearChat() { chatMessages.value = []; }

function chatQuickAction(action) {
  const prompts = {
    resumir:  'Por favor, faça um resumo conciso deste documento.',
    explicar: 'Explique o conteúdo deste documento de forma clara e simples.',
    pontos:   'Liste os principais pontos e ideias-chave deste documento.',
  };
  chatInput.value = prompts[action] || '';
  sendChatMessage();
}

async function sendChatMessage() {
  const msg = chatInput.value.trim();
  if (!msg || chatStreaming.value) return;
  chatMessages.value.push({ role: 'user', content: msg });
  chatInput.value = '';
  chatStreaming.value = true;
  const assistantIdx = chatMessages.value.length;
  chatMessages.value.push({ role: 'assistant', content: '' });
  await nextTick(() => { if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight; });
  try {
    const response = await fetch('/api/llm/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: chatMessages.value.slice(0, assistantIdx), document_context: text.value }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') break;
        try {
          const parsed = JSON.parse(raw);
          if (parsed.error) throw new Error(parsed.error);
          if (parsed.content) {
            chatMessages.value[assistantIdx].content += parsed.content;
            chatMessages.value = [...chatMessages.value];
            await nextTick(() => { if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight; });
          }
        } catch (e) {
          if (e.message !== 'Unexpected end of JSON input') throw e;
        }
      }
    }
  } catch (error) {
    chatMessages.value[assistantIdx].content = `*Erro: ${error.message}*`;
    chatMessages.value = [...chatMessages.value];
    notify('Erro no chat', error.message, 'error');
  } finally {
    chatStreaming.value = false;
  }
}

async function generateAudioFromMessage(content) {
  if (!content.trim()) return;
  await generateAudio(content);
  notify('Áudio da mensagem enfileirado');
}

// ── Misc ────────────────────────────────────────────────────────────────────
function statusLabel(status) {
  return { queued: 'Na fila', processing: 'Processando', done: 'Concluído', error: 'Erro', cancelled: 'Cancelado' }[status] || status;
}

onMounted(async () => {
  mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'dark' });
  await loadMeta();
  await loadSettings();
  await loadLLMConfig();
  await refreshJobs();
  await loadModel();
  setInterval(refreshJobs, 5000);
});
</script>
