<template>
  <Toast position="bottom-right">
    <template #message="slotProps">
      <div class="abil-toast">
        <img src="/abil.png" alt="Abil" class="abil-toast-icon" />
        <div class="abil-toast-copy">
          <strong>Abil · {{ slotProps.message.summary }}</strong>
          <span v-if="slotProps.message.detail">{{ slotProps.message.detail }}</span>
        </div>
      </div>

      <Dialog v-model:visible="llmTestDialog" modal header="Teste LLM: Fale sobre a fruta Abil" :style="{ width: '560px' }">
        <div class="fg">
          <div style="white-space:pre-wrap;">{{ llmTestOutput }}</div>
        </div>
        <template #footer>
          <Button label="Fechar" severity="secondary" text @click="llmTestDialog = false" />
        </template>
      </Dialog>
    </template>
  </Toast>

  <!-- ── Uploads em andamento (não bloqueante) ───────────────────── -->
  <TransitionGroup name="upload" tag="div" class="upload-tray">
    <div v-for="upload in docUploads" :key="upload.id" class="upload-card">
      <div class="abil-loader-figure sm">
        <span class="abil-loader-ring"></span>
        <img src="/abil.png" alt="Abil" class="abil-loader-icon" />
      </div>
      <div class="upload-card-info">
        <span class="upload-card-title">Processando documento…</span>
        <span class="upload-card-name" :title="upload.name">{{ upload.name }}</span>
      </div>
      <button class="upload-card-cancel" @click="cancelUpload(upload.id)" title="Cancelar processamento">
        <i class="pi pi-times"></i>
      </button>
    </div>
  </TransitionGroup>

  <!-- ── Diálogo: metadados do upload ────────────────────────────── -->
  <Dialog v-model:visible="uploadDialog.visible" modal header="Novo documento" :style="{ width: '480px' }" :closable="true">
    <div class="fg">
      <div class="field">
        <label>Arquivo</label>
        <div class="upload-file-line">
          <i :class="['pi', docIcon(uploadDialog.file?.name)]"></i>
          <span class="upload-file-name">{{ uploadDialog.file?.name }}</span>
        </div>
      </div>
      <div class="field">
        <label>Nome</label>
        <InputText v-model="uploadDialog.name" placeholder="Nome de exibição (opcional)" />
      </div>
      <div class="field">
        <label>Descrição</label>
        <Textarea v-model="uploadDialog.description" rows="2" auto-resize placeholder="Descrição (opcional)" />
      </div>
      <div class="field">
        <label>Metadados</label>
        <div v-for="(row, i) in uploadDialog.metaRows" :key="i" class="meta-row">
          <InputText v-model="row.key" placeholder="chave" class="meta-key" />
          <InputText v-model="row.value" placeholder="valor" class="meta-value" />
          <button class="icon-btn danger" title="Remover" @click="uploadDialog.metaRows.splice(i, 1)">
            <i class="pi pi-trash"></i>
          </button>
        </div>
        <Button label="Adicionar metadado" size="small" text severity="secondary" icon="pi pi-plus" class="mt-xs" @click="uploadDialog.metaRows.push({ key: '', value: '' })" />
      </div>
    </div>
    <template #footer>
      <Button label="Cancelar" severity="secondary" text @click="uploadDialog.visible = false" />
      <Button label="Processar" icon="pi pi-cog" :disabled="!uploadDialog.file" @click="confirmUpload" />
    </template>
  </Dialog>

  <!-- ── Diálogo: editar documento ────────────────────────────────── -->
  <Dialog v-model:visible="editDialog.visible" modal header="Editar documento" :style="{ width: '480px' }">
    <div class="fg">
      <div class="field">
        <label>Nome</label>
        <InputText v-model="editDialog.name" placeholder="Nome de exibição" />
      </div>
      <div class="field">
        <label>Descrição</label>
        <Textarea v-model="editDialog.description" rows="2" auto-resize placeholder="Descrição (opcional)" />
      </div>
      <div class="field">
        <label>Metadados</label>
        <div v-for="(row, i) in editDialog.metaRows" :key="i" class="meta-row">
          <InputText v-model="row.key" placeholder="chave" class="meta-key" />
          <InputText v-model="row.value" placeholder="valor" class="meta-value" />
          <button class="icon-btn danger" title="Remover" @click="editDialog.metaRows.splice(i, 1)">
            <i class="pi pi-trash"></i>
          </button>
        </div>
        <Button label="Adicionar metadado" size="small" text severity="secondary" icon="pi pi-plus" class="mt-xs" @click="editDialog.metaRows.push({ key: '', value: '' })" />
      </div>
    </div>
    <template #footer>
      <Button label="Cancelar" severity="secondary" text @click="editDialog.visible = false" />
      <Button label="Salvar" icon="pi pi-check" :loading="editDialog.saving" @click="saveDocumentMetadata" />
    </template>
  </Dialog>

  <div class="app-shell">

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
          accept=".txt,.md,.markdown,.html,.htm,.rtf,.docx,.pdf,.epub"
          custom-upload
          :auto="true"
          @uploader="uploadDocument"
          class="tb-upload"
        />
        <div class="tb-sep"></div>
        <Button icon="pi pi-clipboard" label="Colar" size="small" severity="secondary" text @click="pasteClipboard" />
        <!-- Seletor e teste rápido de LLM no editor -->
        <div class="editor-llm-inline" style="display:flex;align-items:center;gap:8px;margin-left:8px;">
          <Dropdown
            v-model="editorLLMModel"
            :options="llmModelOptions"
            option-label="id"
            option-value="id"
            placeholder="Modelo LLM"
            style="min-width:180px"
          />
          <Button class="llm-test-btn" severity="secondary" outlined size="small" @click="quickTestLLM">
            <img src="/abil.svg" alt="abil" style="width:18px;height:18px;margin-right:6px;vertical-align:middle;" /> Testar LLM
          </Button>
        </div>
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

      <!-- Sidebar: módulos do sistema -->
      <nav class="sidebar">
        <template v-for="group in moduleGroups" :key="group.label">
          <span class="sidebar-group-label">{{ group.label }}</span>
          <a
            v-for="v in group.items"
            :key="v.id"
            class="sidebar-item"
            :class="{ active: activeView === v.id }"
            :href="`#${v.id}`"
            :title="v.description"
            @click="selectView(v.id, $event)"
          >
            <i :class="['pi', v.icon]"></i>
            <span class="sidebar-item-label">{{ v.label }}</span>
            <span v-if="v.id === 'generate' && activeJobRunning" class="sidebar-item-badge"></span>
            <span v-if="v.id === 'chat' && chatStreaming" class="sidebar-item-badge chat"></span>
          </a>
        </template>
      </nav>

      <!-- Module area: apenas o módulo ativo é exibido -->
      <main
        class="module-area"
        :class="{ dropping: isDraggingOver }"
        @dragover.prevent="isDraggingOver = true"
        @dragleave.self="isDraggingOver = false"
        @drop.prevent="handleFileDrop"
      >

        <!-- ── Módulo: EDITOR ─────────────────────────────────── -->
        <section v-show="activeView === 'editor'" class="pane editor-pane">
          <div v-if="!text" class="editor-empty">
            <div class="editor-empty-icon">
              <i class="pi pi-file-edit"></i>
            </div>
            <p class="editor-empty-title">Comece a escrever ou abra um documento</p>
            <p class="editor-empty-sub">Suporta TXT, MD, HTML, RTF, DOCX, PDF e EPUB · Arraste um arquivo aqui</p>
            <div class="editor-empty-actions">
              <FileUpload
                mode="basic"
                name="file"
                choose-label="Abrir arquivo"
                accept=".txt,.md,.markdown,.html,.htm,.rtf,.docx,.pdf,.epub"
                custom-upload
                :auto="true"
                @uploader="uploadDocument"
                class="tb-upload-big"
              />
              <Button icon="pi pi-clipboard" label="Colar texto" severity="secondary" outlined @click="pasteClipboard" />
            </div>
          </div>

          <!-- Abrir existente / criar novo dentro do editor -->
          <div v-if="!text" class="editor-empty-extra">
            <div class="editor-extra-row">
              <Button label="Criar novo documento" icon="pi pi-plus" severity="secondary" text @click="() => { clearText(); nextTick(() => document.querySelector('.editor-ta')?.focus()); }" />
            </div>

            <details class="editor-open-existing">
              <summary>Abrir documento existente</summary>
              <div class="editor-doc-cats">
                <div v-if="studioDocuments.length === 0" class="editor-doc-empty">
                  <span>Nenhum documento disponível no Studio.</span>
                  <small>Use "Abrir arquivo" ou o botão "Novo" para criar.</small>
                </div>
                <div v-else>
                  <div v-for="cat in docCategories" :key="cat.category" class="doc-cat">
                    <div class="doc-cat-title">{{ cat.category }} <span class="doc-cat-count">{{ cat.docs.length }}</span></div>
                    <div class="doc-cat-list">
                      <button v-for="d in cat.docs" :key="d.id" class="doc-open-row" @click="openStudioDocumentInEditor(d.id)">
                        <i :class="['pi', docIcon(d.source_name)]"></i>
                        <span class="doc-open-name">{{ d.display_name || d.source_name }}</span>
                        <span class="doc-open-meta">{{ d.block_count }} blocos · {{ formatDocDate(d.updated_at) }}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </details>
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
        </section><!-- /editor -->

            <!-- ─────────── GERAÇÃO ─────────────────────────────── -->
            <div v-show="activeView === 'generate'" class="pane narrow">

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
                      <Dropdown v-if="speakerSelectable" v-model="settings.speaker" :options="speakerOptions" filter />
                      <span v-else class="f-hint">
                        <i class="pi pi-info-circle"></i> Voz definida pelo modelo carregado
                      </span>
                    </div>
                    <div class="field">
                      <label>Idioma</label>
                      <Dropdown v-model="settings.language" :options="languageOptions" />
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
                    <span v-if="!['edge', 'piper'].includes(settings.backend)" class="f-hint">
                      <i class="pi pi-info-circle"></i> Controle nativo disponível no Edge-TTS e Piper
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
                    <div class="btn-row mt-xs">
                      <Button
                        label="Baixar WAV"
                        icon="pi pi-download"
                        severity="secondary"
                        outlined
                        size="small"
                        @click="downloadAudio(activeJob?.id, 'wav')"
                      />
                      <Button
                        label="Baixar MP3"
                        icon="pi pi-download"
                        severity="secondary"
                        outlined
                        size="small"
                        @click="downloadAudio(activeJob?.id, 'mp3')"
                      />
                    </div>
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
                <span>{{ docParagraphs.length }} blocos · {{ textStats }}</span>
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
              <div class="doc-library" :class="{ collapsed: !showDocLibrary }">
                <div class="doc-lib-head">
                  <button
                    class="doc-lib-title"
                    title="Recolher/expandir"
                    :aria-expanded="showDocLibrary"
                    aria-controls="doc-library-body"
                    @click="showDocLibrary = !showDocLibrary"
                  >
                    <i class="pi doc-collapse-chev" :class="showDocLibrary ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
                    <i class="pi pi-folder-open"></i> Documentos carregados
                  </button>
                  <span class="doc-lib-count">
                    {{ filteredStudioDocuments.length }}<template v-if="docLibrarySearch"> de {{ studioDocuments.length }}</template>
                  </span>
                  <div v-show="showDocLibrary" class="doc-lib-actions">
                    <div class="doc-lib-search">
                      <i class="pi pi-search"></i>
                      <input v-model="docLibrarySearch" type="text" placeholder="Filtrar documentos…" />
                      <button v-if="docLibrarySearch" @click="docLibrarySearch = ''" title="Limpar filtro">
                        <i class="pi pi-times"></i>
                      </button>
                    </div>
                    <FileUpload
                      mode="basic"
                      name="file"
                      choose-label="Novo"
                      accept=".txt,.md,.markdown,.html,.htm,.rtf,.docx,.pdf,.epub"
                      custom-upload
                      :auto="true"
                      @uploader="uploadDocument"
                      class="doc-lib-upload"
                    />
                    <button class="doc-lib-icon-btn" title="Atualizar lista" @click="loadStudioDocuments">
                      <i class="pi pi-refresh"></i>
                    </button>
                  </div>
                </div>

                <div v-show="showDocLibrary" id="doc-library-body" class="doc-lib-body">
                <div v-if="studioDocuments.length === 0" class="doc-lib-empty">
                  <i class="pi pi-inbox"></i>
                  <span>Nenhum documento carregado ainda</span>
                  <span class="doc-lib-empty-sub">Use "Novo" acima ou arraste um arquivo para a aplicação</span>
                </div>
                <div v-else-if="filteredStudioDocuments.length === 0" class="doc-lib-empty">
                  <i class="pi pi-search"></i>
                  <span>Nenhum documento encontrado para "{{ docLibrarySearch }}"</span>
                </div>
                <div v-else class="doc-lib-grid">
                  <div
                    v-for="doc in filteredStudioDocuments"
                    :key="doc.id"
                    class="doc-card"
                    :class="{ active: activeDocumentId === doc.id }"
                  >
                    <button class="doc-card-main" :title="docCardTooltip(doc)" @click="openStudioDocument(doc.id)">
                      <span class="doc-card-icon">
                        <i :class="['pi', docIcon(doc.source_name)]"></i>
                      </span>
                      <span class="doc-card-info">
                        <span class="doc-card-name">{{ doc.display_name || doc.source_name }}</span>
                        <span v-if="doc.description" class="doc-card-desc">{{ doc.description }}</span>
                        <span class="doc-card-meta">
                          {{ parserLabel(doc.parser) }} · {{ doc.block_count }} blocos · {{ formatDocDate(doc.updated_at) }}
                        </span>
                      </span>
                    </button>
                    <span class="doc-card-acts">
                      <i v-if="activeDocumentId === doc.id" class="pi pi-check-circle doc-card-check"></i>
                      <button class="doc-act" title="Editar nome e metadados" @click.stop="openEditDialog(doc)">
                        <i class="pi pi-pencil"></i>
                      </button>
                      <button class="doc-act danger" title="Excluir documento" @click.stop="deleteStudioDocument(doc)">
                        <i class="pi pi-trash"></i>
                      </button>
                    </span>
                  </div>
                </div>
                </div><!-- /doc-library-body -->
              </div>
              <!-- Áudios gerados deste documento (player) -->
              <div v-if="activeDocumentId" class="doc-audios" :class="{ collapsed: !showDocAudios }">
                <div class="doc-audios-head">
                  <button
                    class="doc-audios-title"
                    title="Recolher/expandir"
                    :aria-expanded="showDocAudios"
                    aria-controls="doc-audios-body"
                    @click="showDocAudios = !showDocAudios"
                  >
                    <i class="pi doc-collapse-chev" :class="showDocAudios ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
                    <i class="pi pi-headphones"></i> Áudios gerados
                  </button>
                  <span class="doc-audios-count">{{ documentJobs.length }}</span>
                  <button v-show="showDocAudios" class="doc-lib-icon-btn" title="Atualizar áudios" @click.stop="refreshJobs">
                    <i class="pi pi-refresh"></i>
                  </button>
                </div>

                <div v-show="showDocAudios" id="doc-audios-body" class="doc-audios-body">
                <div v-if="documentJobs.length === 0" class="doc-audios-empty">
                  <i class="pi pi-volume-off"></i>
                  <span>Nenhum áudio gerado para este documento ainda</span>
                  <span class="doc-audios-empty-sub">Use "Gerar livro" ou os botões de áudio dos blocos</span>
                </div>

                <div v-else class="doc-audios-list">
                  <div
                    v-for="job in documentJobs"
                    :key="job.id"
                    class="doc-audio-item"
                    :class="job.status"
                  >
                    <div class="doc-audio-row">
                      <span class="status-dot sm" :class="job.status"></span>
                      <div class="doc-audio-meta">
                        <span class="doc-audio-name">
                          {{ activeDocLabel }}
                          <span class="doc-audio-badge" :class="job.status">{{ statusLabel(job.status) }}</span>
                        </span>
                        <span class="doc-audio-sub">
                          {{ job.backend }}<template v-if="job.speaker"> · {{ job.speaker }}</template> · {{ job.input_words }} palavras
                        </span>
                      </div>
                      <div class="doc-audio-acts">
                        <button
                          v-if="job.status === 'done'"
                          class="doc-act"
                          title="Baixar WAV"
                          @click="downloadAudio(job.id, 'wav')"
                        >
                          <i class="pi pi-download"></i>
                        </button>
                        <button
                          v-if="job.status === 'done'"
                          class="doc-act"
                          title="Baixar MP3"
                          @click="downloadAudio(job.id, 'mp3')"
                        >
                          <span class="doc-act-txt">MP3</span>
                        </button>
                        <button
                          v-if="canCancel(job)"
                          class="doc-act warn"
                          title="Cancelar geração"
                          @click="cancelJob(job.id)"
                        >
                          <i class="pi pi-stop-circle"></i>
                        </button>
                        <button class="doc-act danger" title="Remover áudio" @click="deleteJob(job.id)">
                          <i class="pi pi-trash"></i>
                        </button>
                      </div>
                    </div>

                    <audio
                      v-if="job.status === 'done'"
                      :src="`/api/audio/${job.id}`"
                      controls
                      preload="none"
                      class="doc-audio-player"
                    ></audio>
                    <div v-else-if="canCancel(job)" class="doc-audio-progress">
                      <ProgressBar :value="job.progress || 0" />
                      <span class="doc-audio-progress-txt">{{ job.message || statusLabel(job.status) }}</span>
                    </div>
                    <div v-else class="doc-audio-failed">
                      <i class="pi pi-exclamation-triangle"></i> {{ job.message || job.error || statusLabel(job.status) }}
                    </div>
                  </div>
                </div>
                </div><!-- /doc-audios-body -->
              </div>

              <div class="doc-toolbar">
                <div class="doc-play-controls">
                  <button
                    class="doc-play-btn main"
                    :class="{ playing: docPlayback.active && !docPlayback.paused }"
                    :disabled="!text.trim() && !docPlayback.active"
                    :title="docPlayback.active && !docPlayback.paused ? 'Pausar leitura' : 'Ler documento com TTS'"
                    @click="onDocPlayClick"
                  >
                    <i :class="['pi', docPlayback.active && !docPlayback.paused ? 'pi-pause' : 'pi-play']"></i>
                  </button>
                  <button class="doc-play-btn" :disabled="!docPlayback.active" title="Parar leitura" @click="stopPlayback()">
                    <i class="pi pi-stop"></i>
                  </button>
                  <span v-if="docPlayback.active" class="doc-play-status">
                    <span v-if="docPlayback.loading"><i class="pi pi-spin pi-spinner"></i> Sintetizando…</span>
                    <span v-else-if="docPlayback.paused">Pausado</span>
                    <span v-else>Lendo § {{ docPlayback.idx + 1 }}</span>
                  </span>
                </div>
                <div class="chat-quick-btns">
                  <button class="quick-btn" :class="{ active: documentMode === 'document' }" :disabled="!activeDocumentId" @click="setDocumentMode('document')">
                    Documento
                  </button>
                  <button class="quick-btn" :class="{ active: documentMode === 'tts' }" :disabled="!activeDocumentId" @click="setDocumentMode('tts')">
                    Modo TTS
                  </button>
                  <button class="quick-btn" :disabled="!activeDocumentId || !docBlocks.length" @click="startBlockEditor" title="Editar blocos e escolher o que ignorar">
                    <i class="pi pi-list"></i> Editar blocos
                  </button>
                  <button class="quick-btn" :disabled="!activeDocumentId || !docBlocks.length" @click="generateDocumentAudio" title="Gerar áudio do documento inteiro (blocos incluídos)">
                    <i class="pi pi-bolt"></i> Gerar livro
                  </button>
                </div>
                <div class="doc-search-wrap">
                  <i class="pi pi-search doc-search-icon"></i>
                  <input
                    ref="docSearchInputEl"
                    v-model="docSearch"
                    type="text"
                    class="doc-search-input"
                    placeholder="Buscar no documento… ( / )"
                    @keydown.escape="docSearch = ''"
                  />
                  <button v-if="docSearch" class="doc-search-clear" @click="docSearch = ''">
                    <i class="pi pi-times"></i>
                  </button>
                </div>
                <button
                  v-if="hasOutline"
                  class="quick-btn ml-auto"
                  :class="{ active: showOutline }"
                  title="Mostrar/ocultar sumário do documento"
                  @click="showOutline = !showOutline"
                >
                  <i class="pi pi-list"></i> Sumário
                </button>
                <label class="tog small" :class="{ 'ml-auto': !hasOutline }">
                  <Checkbox v-model="docFollowTTS" binary />
                  <span>Acompanhar TTS</span>
                </label>
              </div>
              <!-- Editor de blocos -->
              <div v-if="docEditing" class="block-editor">
                <div class="be-head">
                  <span class="be-title"><i class="pi pi-list"></i> Editar blocos</span>
                  <span class="be-count">{{ includedCount }} incluídos · {{ editingBlocks.length - includedCount }} ignorados</span>
                  <div class="be-actions">
                    <Button label="Gerar áudio do documento" icon="pi pi-bolt" size="small" :disabled="!includedCount" @click="generateDocumentAudio" />
                    <Button label="Salvar" icon="pi pi-check" size="small" severity="secondary" outlined :loading="savingBlocks" @click="saveDocumentBlocks" />
                    <Button label="Cancelar" size="small" severity="secondary" text @click="docEditing = false" />
                  </div>
                </div>
                <div class="be-list">
                  <div
                    v-for="(block, i) in editingBlocks"
                    :key="i"
                    class="be-row"
                    :class="[`be-t-${block.type}`, { excluded: !block.include }]"
                  >
                    <input type="checkbox" class="be-check" v-model="block.include" :title="block.include ? 'Ignorar na geração e leitura' : 'Incluir na geração e leitura'" />
                    <div class="be-main">
                      <div class="be-meta">
                        <span class="be-num">#{{ i + 1 }}</span>
                        <span class="be-type">{{ block.type }}<template v-if="block.level"> · h{{ block.level }}</template></span>
                        <button v-if="block.type === 'heading'" class="be-section-btn" @click="toggleSection(i)">
                          {{ block.include ? 'Ignorar seção' : 'Incluir seção' }}
                        </button>
                      </div>
                      <textarea v-model="block.text" class="be-text" rows="2"></textarea>
                    </div>
                  </div>
                </div>
              </div>

              <template v-else>
              <div class="doc-stats-bar">
                <span>{{ filteredParagraphs.length }} / {{ docParagraphs.length }} blocos</span>
                <span v-if="docCurrentPara >= 0" class="doc-progress-txt">
                  Reproduzindo § {{ docCurrentPara + 1 }}
                </span>
                <span class="doc-nav-hint">↑↓/j k navegar · Enter ler · Espaço play/pause · / buscar</span>
              </div>

              <div class="doc-nav-layout">
                <!-- Sumário / outline -->
                <aside v-if="showOutline && hasOutline" class="doc-outline">
                  <div class="doc-outline-head"><i class="pi pi-list"></i> Sumário</div>
                  <nav class="doc-outline-list">
                    <button
                      v-for="h in docOutline"
                      :key="h.idx"
                      class="doc-outline-item"
                      :class="[`lvl-${h.level}`, { active: h.idx === docCurrentSectionIdx }]"
                      :title="h.text"
                      @click="jumpToBlock(h.idx)"
                    >{{ h.text }}</button>
                  </nav>
                </aside>

                <div class="doc-viewer-wrap">
                  <!-- Seção atual fixa (sticky) -->
                  <div v-if="docCurrentSection" class="doc-current-section" @click="jumpToBlock(docCurrentSection.idx)">
                    <i class="pi pi-bookmark"></i>
                    <span>{{ docCurrentSection.text }}</span>
                  </div>

                  <div class="doc-viewer" ref="docViewerEl" @scroll="onDocScroll">
                <div v-if="!text.trim()" class="doc-empty">
                  <i class="pi pi-file"></i>
                  <p>Carregue um documento para visualizar aqui.</p>
                </div>
                <div v-else-if="filteredParagraphs.length === 0" class="doc-empty">
                  <i class="pi pi-search"></i>
                  <p>Nenhum parágrafo encontrado para "{{ docSearch }}"</p>
                </div>
                <template v-else>
                  <div
                    v-for="block in filteredParagraphs"
                    :key="block.originalIdx"
                    :data-idx="block.originalIdx"
                    class="doc-p doc-block"
                    :class="[`doc-t-${block.type}`, {
                      active: block.originalIdx === docCurrentPara,
                      highlighted: block.hasMatch && docSearch,
                      excluded: block.exclude && documentMode !== 'tts',
                      playing: docPlayback.active && docPlayback.idx === block.originalIdx,
                      'play-paused': docPlayback.active && docPlayback.paused && docPlayback.idx === block.originalIdx
                    }]"
                    @click="jumpToParaInEditor(block.originalIdx)"
                  >
                    <span class="doc-para-num">{{ block.originalIdx + 1 }}</span>
                    <span
                      v-if="docPlayback.active && docPlayback.idx === block.originalIdx"
                      class="doc-eq"
                      :title="docPlayback.paused ? 'Pausado' : 'Lendo este bloco'"
                    >
                      <span></span><span></span><span></span>
                    </span>
                    <div class="doc-block-body">
                      <div class="doc-block-actions" @click.stop>
                        <button
                          v-if="documentMode !== 'tts' && docBlocks.length"
                          class="doc-act"
                          :class="{ on: block.exclude }"
                          :title="block.exclude ? 'Incluir bloco' : 'Ignorar bloco'"
                          @click="toggleBlockExcluded(block.originalIdx)"
                        >
                          <i :class="['pi', block.exclude ? 'pi-eye' : 'pi-eye-slash']"></i>
                        </button>
                        <button
                          class="doc-act"
                          :class="{ on: docPlayback.active && docPlayback.idx === block.originalIdx }"
                          title="Ler a partir daqui"
                          @click="playFromBlock(block.originalIdx)"
                        >
                          <i class="pi pi-play"></i>
                        </button>
                        <button class="doc-act" title="Gerar áudio deste bloco" @click="generateBlockAudio(block)">
                          <i class="pi pi-volume-up"></i>
                        </button>
                        <button
                          v-if="block.type === 'heading' && documentMode !== 'tts'"
                          class="doc-act chapter"
                          title="Gerar áudio do capítulo"
                          @click="generateChapterAudio(block.originalIdx)"
                        >
                          <i class="pi pi-book"></i>
                        </button>
                      </div>
                      <span v-if="block.hasMatch && docSearch" v-html="block.html"></span>

                      <component
                        :is="'h' + Math.min(Math.max(block.level || 2, 1), 6)"
                        v-else-if="block.type === 'heading'"
                        class="doc-heading"
                      >{{ block.text.replace(/^#{1,6}\s+/, '') }}</component>

                      <div
                        v-else-if="block.type === 'equation'"
                        class="doc-equation"
                        v-html="renderEquation(block.text)"
                      ></div>

                      <pre v-else-if="block.type === 'code'" class="doc-code"><code>{{ block.text.replace(/^\s*```[a-zA-Z0-9]*\n?/, '').replace(/```\s*$/, '') }}</code></pre>

                      <div
                        v-else-if="block.type === 'table'"
                        class="doc-table-wrap"
                        v-html="renderTable(block.text)"
                      ></div>

                      <ul v-else-if="block.type === 'list'" class="doc-list">
                        <li v-for="(item, li) in listItems(block.text)" :key="li">{{ item }}</li>
                      </ul>

                      <p v-else-if="block.type === 'reference'" class="doc-ref">
                        <i class="pi pi-book"></i> {{ block.text }}
                      </p>

                      <p v-else class="doc-text">{{ block.text }}</p>
                    </div>
                  </div>
                </template>
                  </div><!-- /doc-viewer -->

                  <!-- Minimapa de progresso / navegação -->
                  <div
                    v-if="hasOutline"
                    class="doc-minimap"
                    title="Clique para pular no documento"
                    @click="onMinimapClick"
                  >
                    <span
                      v-for="m in docMinimapMarks"
                      :key="m.idx"
                      class="doc-minimap-mark"
                      :class="[`lvl-${m.level}`, { active: m.idx === docCurrentSectionIdx }]"
                      :style="{ top: (m.pct * 100) + '%' }"
                    ></span>
                    <span class="doc-minimap-thumb" :style="{ top: (docScrollPct * 100) + '%' }"></span>
                    <span
                      v-if="docPlayback.active && docParagraphs.length > 1"
                      class="doc-minimap-playing"
                      :style="{ top: (docPlayback.idx / (docParagraphs.length - 1) * 100) + '%' }"
                    ></span>
                  </div>
                </div><!-- /doc-viewer-wrap -->
              </div><!-- /doc-nav-layout -->

              <audio ref="docAudioEl" class="doc-hidden-audio" preload="auto"></audio>
              </template>
            </div><!-- /document -->

            <!-- ─────────── LLM ───────────────────────────────── -->
            <div v-show="activeView === 'llm'" class="pane narrow">

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
                    <button class="action-tile" @click="translateDocument" :disabled="!text.trim() || llmTranslating" :class="{ loading: llmTranslating }">
                      <i class="pi pi-language"></i>
                      <span>Traduzir para PT-BR</span>
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
            <div v-show="activeView === 'diagram'" class="pane narrow">
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
            <div v-show="activeView === 'models'" class="pane narrow">

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

        <div v-if="isDraggingOver" class="drop-overlay">
          <i class="pi pi-upload"></i>
          <span>Solte o arquivo para abrir</span>
        </div>

      </main><!-- /module-area -->

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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useToast } from 'primevue/usetoast';
import { marked } from 'marked';
import mermaid from 'mermaid';
import katex from 'katex';
import 'katex/dist/katex.min.css';

const toast = useToast();

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
  if (!text) return '';
  return marked.parse(text);
}

// ── Typed block rendering ──────────────────────────────────────────────────
function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function cleanEquationText(value) {
  return value
    .replace(/^\s*(?:\$\$|\\\[|\\\()\s*/, '')
    .replace(/\s*(?:\$\$|\\\]|\\\))\s*$/, '')
    .replace(/\\begin\{(equation|align|gather|eqnarray|multline)\*?\}/, '')
    .replace(/\\end\{(equation|align|gather|eqnarray|multline)\*?\}/, '')
    .replace(/&=|&\s*/g, (m) => (m === '&=' ? ' = ' : ' '))
    .trim();
}

function renderEquation(value) {
  const source = cleanEquationText(value);
  try {
    return katex.renderToString(source, { displayMode: true, throwOnError: false, output: 'html', strict: 'ignore' });
  } catch {
    return `<code>${escapeHtml(source)}</code>`;
  }
}

function renderTable(value) {
  const lines = value.split('\n').map(l => l.trim()).filter(Boolean);
  const rows = lines
    .filter(line => line.startsWith('|') || line.toLowerCase().startsWith('tabela:'))
    .map(line => line.replace(/^tabela:\s*/i, ''))
    .map(line => line.replace(/^\||\|$/g, ''))
    .map(line => line.split('|').map(cell => cell.trim()))
    .filter(cells => !cells.every(cell => /^:?-{3,}:?$/.test(cell)));
  if (!rows.length) return `<p>${escapeHtml(value)}</p>`;
  const [head, ...body] = rows;
  const thead = `<thead><tr>${head.map(cell => `<th>${escapeHtml(cell)}</th>`).join('')}</tr></thead>`;
  const tbody = `<tbody>${body.map(cells => `<tr>${cells.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`;
  return `<table class="doc-table">${thead}${tbody}</table>`;
}

function listItems(value) {
  return value
    .split('\n')
    .map(line => line.replace(/^\s*(?:[-*+]|\d+[.)])\s+/, '').trim())
    .filter(Boolean);
}

// ── Navigation: módulos do sistema ─────────────────────────────────────────
const moduleGroups = [
  { label: 'Edição', items: [
    { id: 'editor',   label: 'Editor',    icon: 'pi-file-edit',   description: 'Escreva, cole ou arraste o texto' },
    { id: 'document', label: 'Documento', icon: 'pi-file',        description: 'Biblioteca e visualizador de documentos' },
  ]},
  { label: 'Produção', items: [
    { id: 'generate', label: 'Geração',   icon: 'pi-play-circle', description: 'Gerar áudio com TTS' },
    { id: 'diagram',  label: 'Diagrama',  icon: 'pi-sitemap',     description: 'Gerar fluxograma Mermaid' },
  ]},
  { label: 'Inteligência', items: [
    { id: 'chat',     label: 'Chat',      icon: 'pi-comments',    description: 'Converse com o documento' },
    { id: 'llm',      label: 'LLM',       icon: 'pi-bolt',        description: 'Provedor, modelo e ações de IA' },
  ]},
  { label: 'Sistema', items: [
    { id: 'models',   label: 'Modelos',   icon: 'pi-sliders-h',   description: 'Backends TTS e chaves de API' },
  ]},
];
const activeView = ref('editor');

// ── Deep-linking das abas via hash (#editor, #document, …) ─────────────────
const viewIds = moduleGroups.flatMap(group => group.items.map(item => item.id));

function viewFromHash() {
  const id = (window.location.hash || '').replace(/^#\/?/, '');
  return viewIds.includes(id) ? id : null;
}

function selectView(id, event) {
  // Deixa o clique normal atualizar o hash; só evitamos a navegação em nova aba.
  if (event && (event.metaKey || event.ctrlKey || event.button === 1)) return;
  if (event) event.preventDefault();
  activeView.value = id;
}

function syncHashToView() {
  const target = viewFromHash();
  if (target) activeView.value = target;
}

watch(activeView, (id) => {
  if (viewFromHash() !== id) {
    window.history.replaceState(null, '', `#${id}`);
  }
});

// ── Drag & Drop ────────────────────────────────────────────────────────────
const isDraggingOver = ref(false);
const editorFocused = ref(false);

async function handleFileDrop(event) {
  isDraggingOver.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (!file) return;
  openUploadDialog(file);
}

// ── Core state ─────────────────────────────────────────────────────────────
const text = ref('');
const studioDocuments = ref([]);
const docBlocks = ref([]);
const activeDocumentId = ref(null);
const documentMode = ref('document');
const meta = reactive({
  backends: [],
  speakers: [],
  edge_voices: [],
  voices: {},
  backend_languages: {},
  coqui_models: [],
  languages: [],
  default_backend: 'edge',
  default_device: 'cpu',
});
const settings = reactive({
  backend: 'edge',
  device: 'cpu',
  speaker: 'Ryan',
  language: 'Portuguese',
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
const llmTranslating = ref(false);
const llmResult = ref('');
const llmResultLabel = ref('');

// ── Chat state ─────────────────────────────────────────────────────────────
const chatMessages = ref([]);
const chatInput = ref('');
const chatStreaming = ref(false);
const chatContainer = ref(null);

// Editor LLM quick test state
const editorLLMModel = ref('');
const llmTestOutput = ref('');
const llmTestDialog = ref(false);

watch(llmModelOptions, (v) => {
  if (!editorLLMModel.value && v.length) editorLLMModel.value = v[0].id || v[0];
});

watch(editorLLMModel, async (val, oldVal) => {
  if (!val || val === oldVal) return;
  try {
    // Update server-side LLM config with new model selection
    llmConfig.model = val;
    await saveLLMConfig();
    notify('Modelo LLM selecionado', val, 'success');
  } catch (e) {
    notify('Falha ao selecionar modelo', e.message || String(e), 'error');
  }
});

async function quickTestLLM() {
  // Prompt fixed as requested
  const prompt = 'Fale sobre a fruta Abil.';
  try {
    const res = await api('/api/llm/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: prompt }),
    });
    llmTestOutput.value = res.text || JSON.stringify(res);
    llmTestDialog.value = true;
    notify('Resposta recebida', '', 'success');
  } catch (e) {
    notify('Erro no teste LLM', e.message || String(e), 'error');
  }
}

// ── Document viewer state ──────────────────────────────────────────────────
const docFollowTTS = ref(true);
const docCurrentPara = ref(-1);
const docViewerEl = ref(null);
const docSearch = ref('');
const docSearchInputEl = ref(null);
// Navegação: sumário/outline, seção atual (sticky) e progresso de rolagem.
const showOutline = ref(true);
// Seções recolhíveis para maximizar o espaço do viewer de blocos.
const showDocLibrary = ref(true);
const showDocAudios = ref(false);
const docCurrentSectionIdx = ref(-1); // heading (originalIdx) visível no topo
const docScrollPct = ref(0);          // 0..1 posição de rolagem (minimapa)
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
const speakerOptions = computed(() => {
  const perBackend = meta.voices?.[settings.backend];
  if (perBackend) return perBackend;
  // Fallback for older API responses without the per-backend `voices` map.
  return settings.backend === 'edge' ? meta.edge_voices : meta.speakers;
});
// Piper's voice comes from the loaded .onnx model, so there is nothing to pick.
const speakerSelectable = computed(() => speakerOptions.value.length > 0);
// Languages supported by the selected backend (falls back to the full list).
const languageOptions = computed(() =>
  meta.backend_languages?.[settings.backend] || meta.languages
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
// Áudios gerados a partir do documento aberto (jobs marcados com document_id).
const documentJobs = computed(() => {
  if (!activeDocumentId.value) return [];
  return jobs.value.filter(job => job.document_id === activeDocumentId.value);
});
const canGenerate = computed(() =>
  text.value.trim().length > 0 && modelStatus.status === 'ready'
);
const docParagraphs = computed(() => {
  // Modo "documento": blocos tipados extraídos; modo "tts"/sem blocos: texto plano.
  if (documentMode.value !== 'tts' && docBlocks.value.length) {
    return docBlocks.value.map((block, originalIdx) => ({ ...block, originalIdx }));
  }
  if (!text.value.trim()) return [];
  return text.value
    .split(/\n{2,}/)
    .map(p => p.replace(/\n/g, ' ').trim())
    .filter(Boolean)
    .map((p, originalIdx) => ({ type: 'paragraph', text: p, level: 0, originalIdx }));
});

const filteredParagraphs = computed(() => {
  const q = docSearch.value.trim().toLowerCase();
  return docParagraphs.value.map((block) => {
    if (!q) return { ...block, hasMatch: false, html: '' };
    const hasMatch = block.text.toLowerCase().includes(q);
    if (!hasMatch) return null;
    const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const html = escapeHtml(block.text).replace(new RegExp(escaped, 'gi'), match => `<mark>${match}</mark>`);
    return { ...block, hasMatch: true, html };
  }).filter(Boolean);
});

// Sumário: apenas headings, com o texto limpo e o índice original do bloco.
const docOutline = computed(() =>
  docParagraphs.value
    .filter(b => b.type === 'heading')
    .map(b => ({
      idx: b.originalIdx,
      level: Math.min(Math.max(b.level || 1, 1), 6),
      text: b.text.replace(/^#{1,6}\s+/, '').trim(),
    }))
);
const hasOutline = computed(() => docOutline.value.length > 0);

// Texto da seção atual (barra sticky) derivado do heading visível no topo.
const docCurrentSection = computed(() => {
  const idx = docCurrentSectionIdx.value;
  if (idx < 0) return null;
  return docOutline.value.find(h => h.idx === idx) || null;
});

// Marcadores do minimapa (headings + bloco em reprodução), posicionados pela
// fração do índice no documento.
const docMinimapMarks = computed(() => {
  const total = docParagraphs.value.length;
  if (total <= 1) return [];
  return docOutline.value.map(h => ({
    idx: h.idx,
    level: h.level,
    pct: h.idx / (total - 1),
  }));
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
  if (!job || !docFollowTTS.value || docPlayback.active) return;
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

// Recalcula seção atual/progresso quando o documento muda ou a aba é aberta.
watch([activeView, () => docParagraphs.value.length], () => {
  if (activeView.value !== 'document') return;
  nextTick(onDocScroll);
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
  reconcileVoiceAndLanguage();
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

function reconcileVoiceAndLanguage() {
  if (!speakerOptions.value.includes(settings.speaker)) {
    settings.speaker = speakerOptions.value[0] || 'Ryan';
  }
  if (!languageOptions.value.includes(settings.language)) {
    settings.language = languageOptions.value.includes('Portuguese')
      ? 'Portuguese'
      : (languageOptions.value[0] || 'Portuguese');
  }
}

async function onModelChange() {
  reconcileVoiceAndLanguage();
  await saveSettings();
  await loadModel();
}

// ── Document upload ────────────────────────────────────────────────────────
const docUploads = ref([]);
let uploadSeq = 0;

const uploadDialog = reactive({
  visible: false,
  file: null,
  name: '',
  description: '',
  metaRows: [{ key: '', value: '' }],
});

function openUploadDialog(file) {
  if (!file) return;
  uploadDialog.file = file;
  uploadDialog.name = file.name.replace(/\.[^.]+$/, '');
  uploadDialog.description = '';
  uploadDialog.metaRows = [{ key: '', value: '' }];
  uploadDialog.visible = true;
}

function confirmUpload() {
  const file = uploadDialog.file;
  if (!file) return;
  const meta = {};
  for (const row of uploadDialog.metaRows) {
    const key = (row.key || '').trim();
    if (key) meta[key] = (row.value || '').trim();
  }
  startDocumentUpload(file, {
    name: uploadDialog.name.trim(),
    description: uploadDialog.description.trim(),
    meta,
  });
  uploadDialog.visible = false;
}

function docIcon(name) {
  const ext = (name || '').split('.').pop().toLowerCase();
  if (ext === 'pdf') return 'pi-file-pdf';
  if (['docx', 'rtf'].includes(ext)) return 'pi-file-word';
  if (['epub', 'mobi'].includes(ext)) return 'pi-book';
  if (['html', 'htm'].includes(ext)) return 'pi-globe';
  return 'pi-file';
}

function parserLabel(parser) {
  return parser === 'docling' ? 'Docling + OCR' : 'leitor local';
}

function docCardTooltip(document) {
  const lines = [document.display_name || document.source_name];
  if (document.description) lines.push(document.description);
  const meta = document.meta || {};
  const entries = Object.entries(meta);
  if (entries.length) lines.push(entries.map(([key, value]) => `${key}: ${value}`).join(' · '));
  return lines.join('\n');
}

function formatDocDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

async function startDocumentUpload(file, options = {}) {
  const id = ++uploadSeq;
  const controller = new AbortController();
  docUploads.value.push({ id, name: file.name, controller });
  const form = new FormData();
  form.append('file', file);
  if (options.name) form.append('name', options.name);
  if (options.description) form.append('description', options.description);
  if (options.meta && Object.keys(options.meta).length) form.append('metadata', JSON.stringify(options.meta));
  try {
    const result = await api('/api/upload', { method: 'POST', body: form, signal: controller.signal });
    applyUploadedDocument(result, options.name || file.name);
  } catch (error) {
    if (controller.signal.aborted || error.name === 'AbortError') {
      notify('Processamento cancelado', file.name, 'warn');
    } else {
      notify('Falha ao abrir documento', error.message, 'error');
    }
  } finally {
    docUploads.value = docUploads.value.filter(upload => upload.id !== id);
  }
}

function cancelUpload(id) {
  docUploads.value.find(upload => upload.id === id)?.controller.abort();
}

function uploadDocument(event) {
  const file = event.files?.[0];
  if (!file) return;
  openUploadDialog(file);
}

async function loadStudioDocuments() {
  try {
    const result = await api('/api/documents');
    studioDocuments.value = result.documents;
  } catch (error) {
    notify('Falha ao carregar documentos', error.message, 'error');
  }
}

// ── Biblioteca: filtro, edição e exclusão ──────────────────────────────────
const docLibrarySearch = ref('');
const filteredStudioDocuments = computed(() => {
  const q = docLibrarySearch.value.trim().toLowerCase();
  if (!q) return studioDocuments.value;
  return studioDocuments.value.filter(doc => {
    const haystack = [
      doc.display_name,
      doc.source_name,
      doc.description,
      ...Object.values(doc.meta || {}),
    ].filter(Boolean).join(' ').toLowerCase();
    return haystack.includes(q);
  });
});

// Agrupa documentos por categoria (meta.category, meta.categories, meta.tags ou 'Sem categoria')
const docCategories = computed(() => {
  const map = new Map();
  for (const doc of studioDocuments.value) {
    const metaVal = doc.meta || {};
    let catField = metaVal.category || metaVal.categories || metaVal.tags || 'Sem categoria';
    let keys = [];
    if (Array.isArray(catField)) keys = catField.length ? catField : ['Sem categoria'];
    else if (typeof catField === 'string') keys = catField.split(',').map(s => s.trim()).filter(Boolean) || ['Sem categoria'];
    else keys = ['Sem categoria'];
    for (const k of keys) {
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(doc);
    }
  }
  return [...map.entries()].map(([category, docs]) => ({ category, docs }));
});

const editDialog = reactive({
  visible: false,
  id: null,
  name: '',
  description: '',
  metaRows: [{ key: '', value: '' }],
  saving: false,
});

function openEditDialog(doc) {
  editDialog.id = doc.id;
  editDialog.name = doc.display_name || '';
  editDialog.description = doc.description || '';
  editDialog.metaRows = Object.entries(doc.meta || {})
    .map(([key, value]) => ({ key, value: String(value ?? '') }));
  if (!editDialog.metaRows.length) editDialog.metaRows = [{ key: '', value: '' }];
  editDialog.visible = true;
}

async function saveDocumentMetadata() {
  const meta = {};
  for (const row of editDialog.metaRows) {
    const key = (row.key || '').trim();
    if (key) meta[key] = (row.value || '').trim();
  }
  editDialog.saving = true;
  try {
    await api(`/api/documents/${editDialog.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: editDialog.name.trim(),
        description: editDialog.description.trim(),
        meta,
      }),
    });
    editDialog.visible = false;
    await loadStudioDocuments();
    notify('Documento atualizado', '', 'success');
  } catch (error) {
    notify('Falha ao atualizar documento', error.message, 'error');
  } finally {
    editDialog.saving = false;
  }
}

async function deleteStudioDocument(doc) {
  const label = doc.display_name || doc.source_name;
  if (!window.confirm(`Excluir "${label}"? Esta ação não pode ser desfeita.`)) return;
  try {
    await api(`/api/documents/${doc.id}`, { method: 'DELETE' });
    if (activeDocumentId.value === doc.id) clearText();
    await loadStudioDocuments();
    notify('Documento excluído', label);
  } catch (error) {
    notify('Falha ao excluir documento', error.message, 'error');
  }
}

function applyUploadedDocument(result, fileName) {
  text.value = result.text;
  docBlocks.value = result.blocks || [];
  activeDocumentId.value = result.document_id;
  documentMode.value = 'document';
  loadStudioDocuments();
  const parser = result.parser === 'docling' ? 'Docling + OCR' : 'leitor local';
  const detail = result.parser === 'docling'
    ? `${fileName} · OCR pode processar em CPU quando CUDA não estiver disponível.`
    : `${fileName} · ${parser}`;
  notify('Documento salvo no Studio', detail);
}

async function openStudioDocument(documentId) {
  try {
    const result = await api(`/api/documents/${documentId}`);
    text.value = result.text;
    docBlocks.value = result.blocks || [];
    activeDocumentId.value = documentId;
    documentMode.value = 'document';
    docEditing.value = false;
    clearAudioCache();
    // Recolhe a biblioteca para dar espaço máximo ao viewer de blocos.
    showDocLibrary.value = false;
    // Foca/realça o início do documento no viewer.
    docSearch.value = '';
    stopPlayback(true);
    nextTick(() => {
      if (docViewerEl.value) docViewerEl.value.scrollTop = 0;
      const first = filteredParagraphs.value[0];
      docCurrentPara.value = first ? first.originalIdx : -1;
      onDocScroll();
    });
  } catch (error) {
    notify('Falha ao abrir documento', error.message, 'error');
  }
}

// Abre um documento do Studio diretamente no editor (mantém document metadata)
async function openStudioDocumentInEditor(documentId) {
  try {
    const result = await api(`/api/documents/${documentId}`);
    text.value = result.text;
    docBlocks.value = result.blocks || [];
    activeDocumentId.value = documentId;
    documentMode.value = 'document';
    docEditing.value = false;
    clearAudioCache();
    // Fecha a biblioteca para dar espaço
    showDocLibrary.value = false;
    // Vai para a aba editor e foca o textarea
    activeView.value = 'editor';
    nextTick(() => { const ta = document.querySelector('.editor-ta'); ta?.focus(); });
  } catch (error) {
    notify('Falha ao abrir documento', error.message, 'error');
  }
}

async function setDocumentMode(mode) {
  if (!activeDocumentId.value || documentMode.value === mode) return;
  stopPlayback(true);
  try {
    const result = await api(`/api/documents/${activeDocumentId.value}/variant?mode=${mode}&language=${encodeURIComponent(settings.language)}`);
    text.value = result.text;
    documentMode.value = mode;
  } catch (error) {
    notify('Falha ao alterar modo', error.message, 'error');
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
  docBlocks.value = [];
  stopPlayback(true);
  docEditing.value = false;
  activeDocumentId.value = null;
  documentMode.value = 'document';
  audioUrl.value = '';
  docCurrentPara.value = -1;
  diagramSource.value = '';
  diagramSvg.value = '';
}

// ── Document TTS player (com cache e pré-carregamento) ─────────────────────
const docPlayback = reactive({ active: false, paused: false, loading: false, idx: -1 });
const docAudioEl = ref(null);
let playbackAbort = null;
let playbackToken = 0;

// Cache de áudio por assinatura (voz/backend/velocidade/doc) → replay e
// pré-carregamento instantâneos; janela limitada em torno do bloco atual.
const AUDIO_CACHE_MAX = 40;
const audioCache = new Map();      // key -> { idx, url }
const synthInFlight = new Map();   // key -> Promise<url>

function cacheSignature() {
  return [
    settings.backend, settings.speaker, settings.language,
    settings.device, generateOptions.speed,
  ].join('|');
}

function cacheKey(idx) {
  return `${cacheSignature()}::${activeDocumentId.value || 'texto'}::${idx}`;
}

function trimAudioCache(centerIdx) {
  if (audioCache.size <= AUDIO_CACHE_MAX) return;
  const entries = [...audioCache.entries()]
    .sort((a, b) => Math.abs(a[1].idx - centerIdx) - Math.abs(b[1].idx - centerIdx));
  for (const [key] of entries.slice(AUDIO_CACHE_MAX)) {
    URL.revokeObjectURL(audioCache.get(key).url);
    audioCache.delete(key);
  }
}

function clearAudioCache() {
  for (const { url } of audioCache.values()) URL.revokeObjectURL(url);
  audioCache.clear();
}

function synthBlock(block) {
  const key = cacheKey(block.originalIdx);
  const hit = audioCache.get(key);
  if (hit) return Promise.resolve(hit.url);
  if (synthInFlight.has(key)) return synthInFlight.get(key);
  const promise = fetchBlockAudio(block)
    .then(url => {
      audioCache.set(key, { idx: block.originalIdx, url });
      trimAudioCache(block.originalIdx);
      return url;
    })
    .finally(() => synthInFlight.delete(key));
  synthInFlight.set(key, promise);
  return promise;
}

function readableBlocks() {
  return docParagraphs.value.filter(block =>
    !block.exclude && !['code', 'reference'].includes(block.type) && (block.tts || block.text).trim()
  );
}

function runPrefetch(targets, token) {
  (async () => {
    for (const block of targets) {
      if (token !== playbackToken) return;
      try { await synthBlock(block); } catch { return; }
    }
  })();
}

function prefetchNeighborhood(startIdx, token) {
  const blocks = readableBlocks();
  const pos = blocks.findIndex(block => block.originalIdx === startIdx);
  if (pos === -1) return;
  const targets = [];
  if (pos > 0) targets.push(blocks[pos - 1]);
  for (let i = pos; i < Math.min(pos + 3, blocks.length); i++) targets.push(blocks[i]);
  runPrefetch(targets, token);
}

function prefetchAhead(queue, fromPos, token) {
  runPrefetch(queue.slice(fromPos, fromPos + 2), token);
}

async function playDocument(fromIdx = 0) {
  const queue = readableBlocks().filter(block => block.originalIdx >= fromIdx);
  if (!queue.length) { notify('Nada para ler', 'Sem blocos legíveis neste documento.', 'warn'); return; }
  stopPlayback(true);
  docPlayback.active = true;
  docPlayback.paused = false;
  playbackAbort = new AbortController();
  const token = ++playbackToken;
  prefetchNeighborhood(queue[0].originalIdx, token);
  for (let i = 0; i < queue.length; i++) {
    if (token !== playbackToken) return;
    const block = queue[i];
    docPlayback.idx = block.originalIdx;
    docCurrentPara.value = block.originalIdx;
    docPlayback.loading = !audioCache.has(cacheKey(block.originalIdx));
    scrollBlockIntoView(block.originalIdx);
    let url;
    try {
      url = await synthBlock(block);
    } catch (error) {
      docPlayback.loading = false;
      if (token === playbackToken) {
        notify('Falha ao sintetizar bloco', error.message, 'error');
        stopPlayback(true);
      }
      return;
    }
    if (token !== playbackToken) return;
    docPlayback.loading = false;
    prefetchAhead(queue, i + 1, token);
    await playAudioUrl(url);
    if (token !== playbackToken) return;
  }
  if (token === playbackToken) {
    stopPlayback(true);
    notify('✓ Leitura concluída', '', 'success');
  }
}

async function fetchBlockAudio(block) {
  const response = await fetch('/api/tts/say', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: block.tts || block.text,
      language: settings.language,
      speaker: settings.speaker,
      backend: settings.backend,
      device: settings.device,
      speed: generateOptions.speed,
      normalize_text: settings.normalize_text,
    }),
    signal: playbackAbort?.signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return URL.createObjectURL(await response.blob());
}

function playAudioUrl(url) {
  return new Promise((resolve) => {
    const audio = docAudioEl.value;
    if (!audio) { resolve(); return; }
    audio.onended = () => resolve();
    audio.onerror = () => resolve();
    audio.src = url;
    audio.play().catch(() => resolve());
  });
}

function onDocPlayClick() {
  if (docPlayback.active) {
    togglePlaybackPause();
    return;
  }
  const from = docCurrentPara.value >= 0 ? docCurrentPara.value : 0;
  playDocument(from);
}

function playFromBlock(idx) {
  playDocument(idx);
}

function togglePlaybackPause() {
  const audio = docAudioEl.value;
  if (!audio) return;
  if (docPlayback.paused) {
    audio.play().catch(() => {});
    docPlayback.paused = false;
  } else {
    audio.pause();
    docPlayback.paused = true;
  }
}

function stopPlayback(silent = false) {
  playbackToken++;
  playbackAbort?.abort();
  const audio = docAudioEl.value;
  if (audio) {
    audio.pause();
    audio.removeAttribute('src');
  }
  docPlayback.active = false;
  docPlayback.paused = false;
  docPlayback.loading = false;
  docPlayback.idx = -1;
  if (!silent) docCurrentPara.value = -1;
}

function scrollBlockIntoView(idx) {
  nextTick(() => {
    docViewerEl.value?.querySelector(`[data-idx="${idx}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}

// ── Navegação do documento (sumário, teclado, minimapa) ─────────────────────
// Índices dos blocos atualmente visíveis (respeita busca/filtro), em ordem.
function visibleBlockIndices() {
  return filteredParagraphs.value.map(b => b.originalIdx);
}

// Marca um bloco como "atual" (cursor de navegação) e rola até ele.
function jumpToBlock(idx, { play = false } = {}) {
  if (idx < 0) return;
  docCurrentPara.value = idx;
  scrollBlockIntoView(idx);
  if (play) playFromBlock(idx);
}

// Move o cursor para o bloco visível anterior/seguinte.
function moveDocFocus(delta) {
  const order = visibleBlockIndices();
  if (!order.length) return;
  const pos = order.indexOf(docCurrentPara.value);
  let next;
  if (pos === -1) {
    next = delta > 0 ? order[0] : order[order.length - 1];
  } else {
    next = order[Math.min(Math.max(pos + delta, 0), order.length - 1)];
  }
  jumpToBlock(next);
}

function focusDocSearch() {
  nextTick(() => docSearchInputEl.value?.focus());
}

// Atualiza seção atual (sticky) e progresso de rolagem (minimapa) ao rolar.
let scrollRaf = 0;
function onDocScroll() {
  if (scrollRaf) return;
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0;
    const el = docViewerEl.value;
    if (!el) return;
    const max = el.scrollHeight - el.clientHeight;
    docScrollPct.value = max > 0 ? Math.min(el.scrollTop / max, 1) : 0;

    if (!hasOutline.value) { docCurrentSectionIdx.value = -1; return; }
    // Último heading cujo topo já passou (ou está perto do topo do viewer).
    const top = el.getBoundingClientRect().top;
    let current = -1;
    for (const h of docOutline.value) {
      const node = el.querySelector(`[data-idx="${h.idx}"]`);
      if (!node) continue;
      if (node.getBoundingClientRect().top - top <= 12) current = h.idx;
      else break;
    }
    docCurrentSectionIdx.value = current === -1 ? docOutline.value[0].idx : current;
  });
}

// Clique no trilho do minimapa → pula para o bloco proporcional à posição.
function onMinimapClick(evt) {
  const total = docParagraphs.value.length;
  if (total === 0) return;
  const rect = evt.currentTarget.getBoundingClientRect();
  const pct = Math.min(Math.max((evt.clientY - rect.top) / rect.height, 0), 1);
  jumpToBlock(Math.round(pct * (total - 1)));
}

// Atalhos de teclado quando a aba Documento está ativa.
function onDocKeydown(evt) {
  if (activeView.value !== 'document') return;
  const tag = (evt.target?.tagName || '').toLowerCase();
  const typing = tag === 'input' || tag === 'textarea' || evt.target?.isContentEditable;
  if (typing) return;
  if (evt.metaKey || evt.ctrlKey || evt.altKey) return;

  switch (evt.key) {
    case 'ArrowDown':
    case 'j':
      evt.preventDefault(); moveDocFocus(1); break;
    case 'ArrowUp':
    case 'k':
      evt.preventDefault(); moveDocFocus(-1); break;
    case 'Home':
      evt.preventDefault(); jumpToBlock(visibleBlockIndices()[0] ?? -1); break;
    case 'End': {
      evt.preventDefault();
      const order = visibleBlockIndices();
      jumpToBlock(order[order.length - 1] ?? -1); break;
    }
    case 'Enter':
      if (docCurrentPara.value >= 0) { evt.preventDefault(); playFromBlock(docCurrentPara.value); }
      break;
    case ' ':
      if (docPlayback.active || docCurrentPara.value >= 0) { evt.preventDefault(); onDocPlayClick(); }
      break;
    case '/':
      evt.preventDefault(); focusDocSearch(); break;
    case 'Escape':
      if (docPlayback.active) stopPlayback();
      else if (docSearch.value) docSearch.value = '';
      break;
    default:
      break;
  }
}

// ── Histórico de escuta ────────────────────────────────────────────────────
const showDocHistory = ref(false);
const docHistory = ref([]);

const activeDocLabel = computed(() => {
  const doc = studioDocuments.value.find(d => d.id === activeDocumentId.value);
  return doc?.display_name || doc?.source_name || 'Texto atual';
});

async function loadDocHistory() {
  try {
    docHistory.value = (await api('/api/listening?limit=60')).history;
  } catch { /* histórico é best-effort */ }
}

async function toggleDocHistory() {
  showDocHistory.value = !showDocHistory.value;
  if (showDocHistory.value) await loadDocHistory();
}

async function clearDocHistory() {
  try {
    await api('/api/listening', { method: 'DELETE' });
    docHistory.value = [];
    notify('Histórico de escuta limpo');
  } catch (error) {
    notify('Falha ao limpar histórico', error.message, 'error');
  }
}

function recordListening(block) {
  if (!activeDocumentId.value) return;
  const doc = studioDocuments.value.find(d => d.id === activeDocumentId.value);
  api('/api/listening', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      document_id: activeDocumentId.value,
      source_name: doc?.source_name || '',
      display_name: doc?.display_name || '',
      block_idx: block.originalIdx,
      snippet: (block.tts || block.text || '').slice(0, 140),
    }),
  }).catch(() => {});
}

function formatTimeAgo(value) {
  if (!value) return '';
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, (Date.now() - then) / 1000);
  if (diff < 60) return 'agora';
  if (diff < 3600) return `${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h`;
  return `${Math.floor(diff / 86400)} d`;
}

async function resumeFromHistory(entry) {
  if (entry.document_id !== activeDocumentId.value) {
    await openStudioDocument(entry.document_id);
  }
  activeView.value = 'document';
  playFromBlock(entry.block_idx);
}

function goToPlayingBlock() {
  activeView.value = 'document';
  if (docPlayback.idx >= 0) scrollBlockIntoView(docPlayback.idx);
}

// ── Editor de blocos e geração do documento ────────────────────────────────
const docEditing = ref(false);
const editingBlocks = ref([]);
const savingBlocks = ref(false);

const includedCount = computed(() => editingBlocks.value.filter(block => block.include).length);

function startBlockEditor() {
  if (!activeDocumentId.value || !docBlocks.value.length) {
    notify('Sem documento estruturado', 'Abra um documento da biblioteca primeiro.', 'warn');
    return;
  }
  stopPlayback(true);
  editingBlocks.value = docBlocks.value.map(block => ({
    type: block.type,
    text: block.text,
    level: block.level || 0,
    include: !block.exclude,
  }));
  docEditing.value = true;
}

function toggleSection(headingIdx) {
  const blocks = editingBlocks.value;
  const heading = blocks[headingIdx];
  const level = heading.level || 1;
  let end = blocks.length;
  for (let i = headingIdx + 1; i < blocks.length; i++) {
    if (blocks[i].type === 'heading' && (blocks[i].level || 1) <= level) { end = i; break; }
  }
  const target = !heading.include;
  for (let i = headingIdx; i < end; i++) blocks[i].include = target;
}

async function putDocumentBlocks(blocks) {
  const result = await api(`/api/documents/${activeDocumentId.value}/blocks`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ blocks }),
  });
  docBlocks.value = result.blocks || [];
  text.value = result.text;
  return result;
}

async function saveDocumentBlocks() {
  if (!activeDocumentId.value) return false;
  savingBlocks.value = true;
  try {
    await putDocumentBlocks(editingBlocks.value.map(({ type, text, level, include }) => ({
      type, text, level, exclude: !include,
    })));
    docEditing.value = false;
    notify('Blocos salvos', '', 'success');
    return true;
  } catch (error) {
    notify('Falha ao salvar blocos', error.message, 'error');
    return false;
  } finally {
    savingBlocks.value = false;
  }
}

async function toggleBlockExcluded(idx) {
  if (!activeDocumentId.value) return;
  try {
    const blocks = docBlocks.value.map((block, i) => ({
      type: block.type,
      text: block.text,
      level: block.level || 0,
      exclude: i === idx ? !block.exclude : !!block.exclude,
    }));
    await putDocumentBlocks(blocks);
    notify(blocks[idx].exclude ? 'Bloco ignorado' : 'Bloco incluído');
  } catch (error) {
    notify('Falha ao atualizar bloco', error.message, 'error');
  }
}

function documentAudioText() {
  return docBlocks.value
    .filter(block => !block.exclude && !['code', 'reference'].includes(block.type))
    .map(block => block.tts || block.text)
    .join('\n\n')
    .trim();
}

async function generateDocumentAudio() {
  if (!activeDocumentId.value || !docBlocks.value.length) {
    notify('Sem documento', 'Abra um documento da biblioteca primeiro.', 'warn');
    return;
  }
  if (docEditing.value && !(await saveDocumentBlocks())) return;
  const audioText = documentAudioText();
  if (!audioText) { notify('Nada para gerar', 'Todos os blocos estão ignorados.', 'warn'); return; }
  generateAudio(audioText);
  notify('Documento na fila', activeDocLabel.value);
}

function generateBlockAudio(block) {
  const blockText = (block.tts || block.text || '').trim();
  if (!blockText) return;
  generateAudio(blockText);
}

function generateChapterAudio(startIdx) {
  const blocks = docBlocks.value;
  const start = blocks[startIdx];
  if (!start) return;
  const level = start.level || 1;
  let end = blocks.length;
  for (let i = startIdx + 1; i < blocks.length; i++) {
    const block = blocks[i];
    if (block.type === 'heading' && (block.level || 1) <= level) { end = i; break; }
  }
  const chapter = blocks.slice(startIdx, end)
    .filter(block => !block.exclude && !['code', 'reference'].includes(block.type))
    .map(block => block.tts || block.text)
    .join('\n\n')
    .trim();
  if (!chapter) { notify('Capítulo vazio', 'Nada a gerar neste capítulo.', 'warn'); return; }
  const title = start.text.replace(/^#{1,6}\s+/, '');
  generateAudio(chapter);
  notify('Capítulo na fila', title, 'info');
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
    documentMode.value = 'tts';
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
        document_id: activeDocumentId.value,
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

function downloadAudio(id, fmt = 'wav') {
  if (!id) return;
  const a = document.createElement('a');
  a.href = `/api/audio/${id}?fmt=${fmt}`;
  a.download = `abil-${id}.${fmt}`;
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

async function translateDocument() {
  if (!text.value.trim()) return;
  llmTranslating.value = true;
  try {
    const endpoint = activeDocumentId.value
      ? `/api/documents/${activeDocumentId.value}/translate`
      : '/api/llm/translate';
    const result = await api(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value, target_language: 'Portuguese (Brazil)' }),
    });
    text.value = result.text;
    settings.language = 'Portuguese';
    documentMode.value = 'document';
    docBlocks.value = result.blocks || docBlocks.value;
    if (activeDocumentId.value) await loadStudioDocuments();
    notify('Documento traduzido para PT-BR', '', 'success');
  } catch (error) {
    notify('Falha na tradução', error.message, 'error');
  } finally {
    llmTranslating.value = false;
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
  syncHashToView();
  window.addEventListener('hashchange', syncHashToView);
  window.addEventListener('keydown', onDocKeydown);
  await loadMeta();
  await loadSettings();
  await loadLLMConfig();
  await loadStudioDocuments();
  await refreshJobs();
  await loadModel();
  setInterval(refreshJobs, 5000);
});

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncHashToView);
  window.removeEventListener('keydown', onDocKeydown);
});
</script>
