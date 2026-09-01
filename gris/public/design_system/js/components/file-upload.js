(() => {
	const SOURCE_LABELS = {
		local: "Meu dispositivo",
		camera: "Câmera",
		web_link: "Link da web",
		library: "Biblioteca",
	};

	const SOURCE_ICONS = {
		local: "hard-drive-upload",
		camera: "camera",
		web_link: "link",
		library: "folder-open",
	};

	function bool(value) {
		return value === true || value === "true" || value === "1";
	}

	function splitList(value) {
		return String(value || "")
			.split(",")
			.map((item) => item.trim())
			.filter(Boolean);
	}

	function getCsrfToken() {
		return window.frappe?.csrf_token || window.csrf_token || "";
	}

	function icon(name) {
		return `<svg class="ds-lucide ds-lucide--sm" aria-hidden="true" focusable="false" viewBox="0 0 24 24"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#${name}" /></svg>`;
	}

	function escapeHtml(value) {
		const element = document.createElement("div");
		element.textContent = String(value || "");
		return element.innerHTML;
	}

	function formatSize(bytes) {
		if (!Number.isFinite(bytes) || bytes <= 0) return "";
		const units = ["B", "KB", "MB", "GB"];
		let size = bytes;
		let unit = 0;

		while (size >= 1024 && unit < units.length - 1) {
			size /= 1024;
			unit += 1;
		}

		return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
	}

	function getExtension(name) {
		const parts = String(name || "")
			.toLowerCase()
			.split(".");
		return parts.length > 1 ? parts.pop() : "";
	}

	function setMessage(component, text, tone = "") {
		const message = component.querySelector("[data-file-upload-message]");
		if (!message) return;

		message.textContent = text || "";
		if (tone) {
			message.dataset.tone = tone;
		} else {
			delete message.dataset.tone;
		}
	}

	function toast(category, title, description) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: { category, title, description },
				},
			})
		);
	}

	const ERRO_GENERICO = "Não foi possível enviar o arquivo. Tente novamente.";

	// O motivo real da recusa vem em `_server_messages`, um JSON aninhado que pode trazer
	// HTML. Sem desempacotar isso, toda falha aparece igual na tela — tipo de arquivo
	// recusado, permissão, configuração ausente — e não há como o usuário se corrigir.
	function serverMessage(error) {
		const raw = error && error._server_messages;
		if (!raw) return error?.exception || "";

		try {
			const mensagens = JSON.parse(raw)
				.map((item) => {
					try {
						return JSON.parse(item).message || "";
					} catch (e) {
						return String(item || "");
					}
				})
				.filter(Boolean);

			if (!mensagens.length) return "";

			const div = document.createElement("div");
			div.innerHTML = mensagens[0];
			return (div.textContent || "").trim();
		} catch (e) {
			return "";
		}
	}

	function getOptions(component) {
		const sources = splitList(component.dataset.sources || "local");
		const allowTakePhoto = bool(component.dataset.allowTakePhoto);
		if (allowTakePhoto && !sources.includes("camera")) {
			sources.push("camera");
		}

		return {
			sources: sources.length ? sources : ["local"],
			allowedExtensions: splitList(component.dataset.allowedExtensions).map((item) =>
				item.replace(/^\./, "").toLowerCase()
			),
			allowMultiple: bool(component.dataset.allowMultiple),
			maxFiles: Number.parseInt(component.dataset.maxFiles || "1", 10) || 1,
			isPrivate: bool(component.dataset.isPrivate),
			allowPrivateChoice:
				bool(component.dataset.allowPrivateChoice) ||
				bool(component.dataset.allowPrivateToggle),
			allowTakePhoto,
			allowOptimize: bool(component.dataset.allowOptimize),
			folder: component.dataset.folder || "Home",
			doctype: component.dataset.doctype || "",
			docname: component.dataset.docname || "",
			fieldname: component.dataset.fieldname || "",
			method: component.dataset.method || "",
			extraParams: parseExtraParams(component.dataset.extraParams),
		};
	}

	// Campos avulsos do FormData, usados por handlers de `method` que precisam saber a que
	// registro o arquivo pertence. Um JSON quebrado não pode derrubar o componente inteiro.
	function parseExtraParams(raw) {
		if (!raw) return {};

		try {
			const parsed = JSON.parse(raw);
			return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
		} catch (error) {
			console.warn("data-extra-params inválido no file-upload.", error);
			return {};
		}
	}

	function updateHiddenValue(component, files) {
		const hidden = component.querySelector("[data-file-upload-value]");
		if (!hidden) return;

		hidden.value =
			files.length > 1
				? JSON.stringify(files.map((file) => file.file_url || ""))
				: files[0]?.file_url || "";
	}

	function validateFiles(component, files, options) {
		if (!files.length) {
			setMessage(component, "Selecione um arquivo para continuar.", "error");
			return [];
		}

		const accepted = [];
		const maxFiles = options.allowMultiple ? options.maxFiles : 1;

		for (const file of files.slice(0, maxFiles)) {
			const extension = getExtension(file.name);
			if (
				options.allowedExtensions.length &&
				!options.allowedExtensions.includes(extension)
			) {
				setMessage(
					component,
					`O arquivo "${file.name}" não está no formato permitido.`,
					"error"
				);
				continue;
			}

			accepted.push({
				id: window.crypto?.randomUUID
					? window.crypto.randomUUID()
					: `${Date.now()}-${Math.random()}`,
				name: file.name,
				size: file.size,
				file,
				progress: 0,
			});
		}

		if (files.length > maxFiles) {
			setMessage(
				component,
				`Apenas ${maxFiles} arquivo(s) podem ser enviados por vez.`,
				"error"
			);
		} else if (accepted.length) {
			setMessage(component, `${accepted.length} arquivo(s) pronto(s) para envio.`);
		}

		return accepted;
	}

	function renderSources(component, state) {
		const wrapper = component.querySelector("[data-file-upload-sources]");
		if (!wrapper) return;

		wrapper.innerHTML = state.options.sources
			.map((source) => {
				const label = SOURCE_LABELS[source] || source;
				const sourceIcon = SOURCE_ICONS[source] || "upload";
				return `
          <button
            type="button"
            class="btn-sm-outline file-upload__source"
            data-file-upload-source="${source}"
            aria-pressed="${source === state.source ? "true" : "false"}"
          >
            ${icon(sourceIcon)}
            <span>${escapeHtml(label)}</span>
          </button>
        `;
			})
			.join("");

		wrapper.hidden = state.options.sources.length <= 1;
	}

	function renderPanels(component, state) {
		component.querySelectorAll("[data-file-upload-panel]").forEach((panel) => {
			panel.hidden = panel.dataset.fileUploadPanel !== state.source;
		});
	}

	function renderFiles(component, state) {
		const list = component.querySelector("[data-file-upload-list]");
		if (!list) return;

		list.innerHTML = state.files
			.map(
				(file) => `
        <article class="file-upload__item" data-file-upload-file="${escapeHtml(file.id)}">
          <div>
            <p class="file-upload__item-name">${escapeHtml(file.name)}</p>
            <p class="file-upload__item-meta">${escapeHtml(formatSize(file.size))}</p>
          </div>
          <button type="button" class="btn-sm-icon-outline file-upload__remove" data-file-upload-remove="${escapeHtml(
				file.id
			)}" aria-label="Remover ${escapeHtml(file.name)}">
            ${icon("x")}
          </button>
          <div class="file-upload__progress" aria-hidden="true">
            <span class="file-upload__progress-bar" style="width: ${file.progress || 0}%"></span>
          </div>
        </article>
      `
			)
			.join("");
	}

	function getPrivateValue(component, options) {
		const input = component.querySelector("[data-file-upload-private]");
		return input ? input.checked : options.isPrivate;
	}

	function getOptimizeValue(component) {
		return Boolean(component.querySelector("[data-file-upload-optimize]")?.checked);
	}

	function uploadOne(component, state, fileState) {
		const options = state.options;

		return new Promise((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			const formData = new FormData();

			if (fileState.file) {
				formData.append("file", fileState.file, fileState.name);
			}

			if (fileState.file_url) {
				formData.append("file_url", fileState.file_url);
			}

			if (fileState.file_name) {
				formData.append("file_name", fileState.file_name);
			}

			if (fileState.library_file_name) {
				formData.append("library_file_name", fileState.library_file_name);
			}

			formData.append("is_private", getPrivateValue(component, options) ? "1" : "0");
			formData.append("folder", options.folder);

			if (options.doctype && options.docname) {
				formData.append("doctype", options.doctype);
				formData.append("docname", options.docname);
			}
			if (options.fieldname) formData.append("fieldname", options.fieldname);
			if (options.method) formData.append("method", options.method);
			// Relido do DOM a cada envio: alguns campos extras dependem do que o usuário
			// digitou depois da página carregar (ex.: o nome que vai no nome do arquivo).
			Object.entries(parseExtraParams(component.dataset.extraParams)).forEach(
				([key, value]) => {
					if (value !== null && value !== undefined) formData.append(key, String(value));
				}
			);
			if (options.allowOptimize && getOptimizeValue(component))
				formData.append("optimize", "true");

			xhr.upload.addEventListener("progress", (event) => {
				if (!event.lengthComputable) return;
				fileState.progress = Math.round((event.loaded / event.total) * 100);
				renderFiles(component, state);
			});

			xhr.addEventListener("load", () => {
				let response = null;
				try {
					response = JSON.parse(xhr.responseText);
				} catch (error) {
					response = { message: xhr.responseText };
				}

				if (xhr.status >= 200 && xhr.status < 300 && response?.message) {
					fileState.progress = 100;
					fileState.doc = response.message;
					renderFiles(component, state);
					resolve(response.message);
					return;
				}

				reject(response);
			});

			xhr.addEventListener("error", () =>
				reject(new Error("Falha de rede ao enviar arquivo."))
			);
			xhr.open("POST", "/api/method/upload_file", true);
			xhr.setRequestHeader("Accept", "application/json");
			const csrfToken = getCsrfToken();
			if (csrfToken) xhr.setRequestHeader("X-Frappe-CSRF-Token", csrfToken);
			xhr.send(formData);
		});
	}

	async function submit(component, state) {
		const submitButton = component.querySelector("[data-file-upload-submit]");
		const dialog = component.querySelector("[data-file-upload-dialog]");
		let uploadFiles = state.files;

		if (state.source === "web_link") {
			const url = component.querySelector("[data-file-upload-web-link]")?.value?.trim();
			if (!url) {
				setMessage(component, "Informe um link válido para continuar.", "error");
				return;
			}
			uploadFiles = [
				{
					id: "web-link",
					name: decodeURI(url).split("/").pop() || url,
					file_url: decodeURI(url),
					progress: 0,
				},
			];
		}

		if (state.source === "library") {
			const libraryFileName = component
				.querySelector("[data-file-upload-library-file]")
				?.value?.trim();
			if (!libraryFileName) {
				setMessage(component, "Informe o arquivo existente para continuar.", "error");
				return;
			}
			uploadFiles = [
				{
					id: "library-file",
					name: libraryFileName,
					library_file_name: libraryFileName,
					progress: 0,
				},
			];
		}

		if (!uploadFiles.length) {
			setMessage(component, "Selecione um arquivo para continuar.", "error");
			return;
		}

		submitButton.disabled = true;
		setMessage(component, "Enviando arquivo...");

		try {
			const uploaded = [];
			for (const file of uploadFiles) {
				uploaded.push(await uploadOne(component, state, file));
			}

			updateHiddenValue(component, uploaded);
			setMessage(component, "Arquivo enviado com sucesso.", "success");
			component.dispatchEvent(
				new CustomEvent("gris:file-upload:success", {
					bubbles: true,
					detail: {
						files: uploaded,
						source: state.source,
						is_private: getPrivateValue(component, state.options),
					},
				})
			);
			dialog?.close();
		} catch (error) {
			const motivo = serverMessage(error) || ERRO_GENERICO;
			setMessage(component, motivo, "error");
			component.dispatchEvent(
				new CustomEvent("gris:file-upload:error", {
					bubbles: true,
					detail: { error, message: motivo },
				})
			);
			toast("error", "Falha no upload", motivo);
		} finally {
			submitButton.disabled = false;
		}
	}

	function initFileUpload(component) {
		const options = getOptions(component);
		const dialog = component.querySelector("[data-file-upload-dialog]");
		const input = component.querySelector("[data-file-upload-input]");
		const cameraInput = component.querySelector("[data-file-upload-camera-input]");
		const dropzone = component.querySelector("[data-file-upload-dropzone]");
		const cameraTrigger = component.querySelector("[data-file-upload-camera-trigger]");
		const state = {
			options,
			source: options.sources[0] || "local",
			files: [],
		};

		renderSources(component, state);
		renderPanels(component, state);

		component.querySelector("[data-file-upload-open]")?.addEventListener("click", () => {
			dialog?.showModal();
		});

		component.querySelectorAll("[data-file-upload-close]").forEach((button) => {
			button.addEventListener("click", () => dialog?.close());
		});

		component.addEventListener("click", (event) => {
			const sourceButton = event.target.closest("[data-file-upload-source]");
			if (sourceButton) {
				state.source = sourceButton.dataset.fileUploadSource;
				state.files = [];
				if (input) input.value = "";
				if (cameraInput) cameraInput.value = "";
				// Sair da aba da câmera precisa desligar o stream, não só esconder o painel.
				pararCamera();
				component.querySelectorAll("[data-file-upload-source]").forEach((button) => {
					button.setAttribute(
						"aria-pressed",
						button === sourceButton ? "true" : "false"
					);
				});
				renderPanels(component, state);
				renderFiles(component, state);
				setMessage(component, "");
			}

			const removeButton = event.target.closest("[data-file-upload-remove]");
			if (removeButton) {
				state.files = state.files.filter(
					(file) => file.id !== removeButton.dataset.fileUploadRemove
				);
				renderFiles(component, state);
				setMessage(
					component,
					state.files.length
						? `${state.files.length} arquivo(s) pronto(s) para envio.`
						: ""
				);
			}
		});

		dropzone?.addEventListener("click", () => input?.click());
		input?.addEventListener("change", () => {
			state.files = validateFiles(component, Array.from(input.files || []), options);
			renderFiles(component, state);
		});

		// Câmera de verdade. O `capture` do input só funciona no celular; no desktop o
		// navegador o ignora e abre o seletor de arquivos, que não é tirar foto. O
		// getUserMedia cobre os dois, e ainda entrega sempre JPEG — o que evita o HEIC do
		// iPhone, recusado pela allowlist de MIME do Frappe.
		const camera = component.querySelector("[data-file-upload-camera]");
		const cameraVideo = component.querySelector("[data-file-upload-camera-video]");
		const cameraShoot = component.querySelector("[data-file-upload-camera-shoot]");
		const cameraCancel = component.querySelector("[data-file-upload-camera-cancel]");

		function pararCamera() {
			const stream = cameraVideo?.srcObject;
			if (stream) {
				stream.getTracks().forEach((track) => track.stop());
				cameraVideo.srcObject = null;
			}
			if (camera) camera.hidden = true;
			if (cameraTrigger) cameraTrigger.hidden = false;
		}

		async function abrirCamera() {
			if (!camera || !cameraVideo || !navigator.mediaDevices?.getUserMedia) {
				cameraInput?.click();
				return;
			}

			try {
				const stream = await navigator.mediaDevices.getUserMedia({
					video: {
						facingMode: { ideal: component.dataset.cameraFacing || "environment" },
					},
					audio: false,
				});
				cameraVideo.srcObject = stream;
				await cameraVideo.play().catch(() => {});
				camera.hidden = false;
				cameraTrigger.hidden = true;
				setMessage(component, "");
			} catch (error) {
				// Permissão negada, sem câmera ou origem insegura: sobra o seletor nativo.
				setMessage(
					component,
					"Não foi possível abrir a câmera. Selecione uma imagem do dispositivo.",
					"error"
				);
				cameraInput?.click();
			}
		}

		function capturarFoto() {
			if (!cameraVideo?.videoWidth) return;

			const canvas = document.createElement("canvas");
			canvas.width = cameraVideo.videoWidth;
			canvas.height = cameraVideo.videoHeight;
			canvas.getContext("2d").drawImage(cameraVideo, 0, 0, canvas.width, canvas.height);

			canvas.toBlob(
				(blob) => {
					if (!blob) return;
					const arquivo = new File([blob], `foto-${Date.now()}.jpg`, {
						type: "image/jpeg",
						lastModified: Date.now(),
					});
					state.files = validateFiles(component, [arquivo], options);
					renderFiles(component, state);
					pararCamera();
				},
				"image/jpeg",
				0.92
			);
		}

		cameraTrigger?.addEventListener("click", abrirCamera);
		cameraShoot?.addEventListener("click", capturarFoto);
		cameraCancel?.addEventListener("click", pararCamera);
		// A luz da câmera não pode continuar acesa depois que o usuário sai do envio.
		dialog?.addEventListener("close", pararCamera);

		cameraInput?.addEventListener("change", () => {
			state.files = validateFiles(component, Array.from(cameraInput.files || []), options);
			renderFiles(component, state);
		});

		dropzone?.addEventListener("dragover", (event) => {
			event.preventDefault();
			dropzone.classList.add("is-dragging");
		});

		dropzone?.addEventListener("dragleave", () => {
			dropzone.classList.remove("is-dragging");
		});

		dropzone?.addEventListener("drop", (event) => {
			event.preventDefault();
			dropzone.classList.remove("is-dragging");
			state.files = validateFiles(
				component,
				Array.from(event.dataTransfer?.files || []),
				options
			);
			renderFiles(component, state);
		});

		component.querySelector("[data-file-upload-submit]")?.addEventListener("click", () => {
			submit(component, state);
		});

		component.dataset.fileUploadInitialized = "true";
		component.dispatchEvent(new CustomEvent("basecoat:initialized"));
	}

	if (window.basecoat) {
		window.basecoat.register(
			"file-upload",
			"[data-file-upload]:not([data-file-upload-initialized])",
			initFileUpload
		);
	}
})();
