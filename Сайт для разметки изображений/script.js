class ImageAnnotationTool {
    constructor() {
        this.canvas = document.getElementById('annotation-canvas');
        this.ctx = this.canvas.getContext('2d');
        
        this.images = [];
        this.currentImageIndex = 0;
        
        // Состояние приложения
        this.isDrawing = false;
        this.startX = 0;
        this.startY = 0;
        
        // Текущая разметка
        this.currentAnnotation = null;
        
        // Для хранения изображения
        this.currentImage = null;
        this.imageWidth = 0;
        this.imageHeight = 0;
        
        // Отображение (размеры на экране)
        this.displayWidth = 0;
        this.displayHeight = 0;
        this.displayRatio = 1;
        
        // Настройки
        this.tool = 'rectangle';
        this.strokeColor = '#ff0000';
        this.fillColor = 'rgba(0, 255, 0, 0.3)';
        
        // Масштабирование
        this.scale = 1;
        this.scaleStep = 0.1;
        this.minScale = 0.1;
        this.maxScale = 5;
        
        // IndexedDB
        this.db = null;
        this.dbReady = this.initDB();
        
        this.initializeElements();
        this.setupEventListeners();
        
        // Восстанавливаем сессию после инициализации БД
        this.dbReady.then(() => {
            this.restoreSession();
        });
    }
    
    // Инициализация IndexedDB
    async initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open('AnnotationToolDB', 1);
            
            request.onerror = () => {
                console.error('❌ Ошибка открытия БД');
                reject(request.error);
            };
            
            request.onsuccess = () => {
                this.db = request.result;
                console.log('✅ IndexedDB готова');
                resolve();
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Хранилище для изображений
                if (!db.objectStoreNames.contains('images')) {
                    const imageStore = db.createObjectStore('images', { keyPath: 'id' });
                    imageStore.createIndex('name', 'name', { unique: false });
                    imageStore.createIndex('timestamp', 'timestamp', { unique: false });
                }
                
                // Хранилище для сессий
                if (!db.objectStoreNames.contains('sessions')) {
                    db.createObjectStore('sessions', { keyPath: 'id' });
                }
                
                console.log('✅ Структура БД создана');
            };
        });
    }
    
    // Сохранение изображения в IndexedDB
    async saveImageToDB(file, annotation = null) {
        const id = `img_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = async (e) => {
                const imageData = {
                    id: id,
                    name: file.name,
                    data: e.target.result, // base64
                    annotation: annotation,
                    timestamp: Date.now(),
                    webkitRelativePath: file.webkitRelativePath || ''
                };
                
                const transaction = this.db.transaction(['images'], 'readwrite');
                const store = transaction.objectStore('images');
                const request = store.add(imageData);
                
                request.onsuccess = () => resolve(id);
                request.onerror = () => reject(request.error);
            };
            reader.readAsDataURL(file);
        });
    }
    
    // Получение изображения из IndexedDB
    async getImageFromDB(id) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['images'], 'readonly');
            const store = transaction.objectStore('images');
            const request = store.get(id);
            
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    
    // Обновление аннотации в БД
    async updateAnnotationInDB(imageId, annotation) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['images'], 'readwrite');
            const store = transaction.objectStore('images');
            
            const getRequest = store.get(imageId);
            
            getRequest.onsuccess = () => {
                const imageData = getRequest.result;
                if (imageData) {
                    imageData.annotation = annotation;
                    const putRequest = store.put(imageData);
                    putRequest.onsuccess = () => resolve();
                    putRequest.onerror = () => reject(putRequest.error);
                }
            };
            
            getRequest.onerror = () => reject(getRequest.error);
        });
    }
    
    // Получение всех изображений из БД
    async getAllImagesFromDB() {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['images'], 'readonly');
            const store = transaction.objectStore('images');
            const request = store.getAll();
            
            request.onsuccess = () => {
                const images = request.result.sort((a, b) => a.timestamp - b.timestamp);
                resolve(images);
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    // Сохранение сессии
    async saveSession() {
        if (!this.db) return;
        
        try {
            const session = {
                id: 'current_session',
                mode: this.elements.multipleImagesRadio.checked ? 'multiple' : 'single',
                tool: this.tool,
                strokeColor: this.strokeColor,
                bgColor: this.elements.bgColor.value,
                saveCropped: this.elements.saveCropped.checked,
                currentImageIndex: this.currentImageIndex,
                imageIds: this.images.map(img => img.id),
                timestamp: Date.now()
            };
            
            const transaction = this.db.transaction(['sessions'], 'readwrite');
            const store = transaction.objectStore('sessions');
            await store.put(session);
            
            console.log('💾 Сессия сохранена в IndexedDB');
        } catch (e) {
            console.error('❌ Ошибка сохранения сессии:', e);
        }
    }
    
    // Восстановление сессии
    async restoreSession() {
        if (!this.db) return;
        
        try {
            const transaction = this.db.transaction(['sessions'], 'readonly');
            const store = transaction.objectStore('sessions');
            const session = await new Promise((resolve) => {
                const request = store.get('current_session');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => resolve(null);
            });
            
            if (!session) {
                console.log('📭 Нет сохраненной сессии');
                return;
            }
            
            console.log('🔄 Восстанавливаем сессию:', session);
            
            // Восстанавливаем настройки
            if (session.mode === 'multiple') {
                this.elements.multipleImagesRadio.checked = true;
                this.elements.singleUpload.style.display = 'none';
                this.elements.folderUpload.style.display = 'block';
                this.elements.nextImage.style.display = 'block';
                if (this.elements.progressInfo) {
                    this.elements.progressInfo.style.display = 'block';
                }
            } else {
                this.elements.singleImageRadio.checked = true;
                this.elements.singleUpload.style.display = 'block';
                this.elements.folderUpload.style.display = 'none';
                this.elements.nextImage.style.display = 'none';
                if (this.elements.progressInfo) {
                    this.elements.progressInfo.style.display = 'none';
                }
            }
            
            this.tool = session.tool || 'rectangle';
            this.elements.toolType.value = this.tool;
            this.strokeColor = session.strokeColor || '#ff0000';
            this.elements.annotationColor.value = this.strokeColor;
            this.elements.bgColor.value = session.bgColor || '#00ff00';
            this.fillColor = this.hexToRgba(this.elements.bgColor.value, 0.3);
            this.elements.saveCropped.checked = session.saveCropped !== false;
            
            // Восстанавливаем изображения
            if (session.imageIds && session.imageIds.length > 0) {
                this.images = [];
                
                for (const id of session.imageIds) {
                    const imgData = await this.getImageFromDB(id);
                    if (imgData) {
                        const response = await fetch(imgData.data);
                        const blob = await response.blob();
                        const file = new File([blob], imgData.name, { type: blob.type });
                        
                        this.images.push({
                            id: imgData.id,
                            file: file,
                            name: imgData.name,
                            url: URL.createObjectURL(file),
                            annotation: imgData.annotation,
                            webkitRelativePath: imgData.webkitRelativePath
                        });
                    }
                }
                
                if (this.images.length > 0) {
                    this.currentImageIndex = Math.min(session.currentImageIndex || 0, this.images.length - 1);
                    
                    if (this.elements.multipleImagesRadio.checked && this.elements.progressInfo) {
                        this.elements.totalCount.textContent = this.images.length;
                        this.elements.processedCount.textContent = this.currentImageIndex + 1;
                        this.elements.progressBar.value = ((this.currentImageIndex + 1) / this.images.length) * 100;
                    }
                    
                    await this.displayCurrentImage();
                    this.updateUI();
                    
                    console.log(`✅ Восстановлено ${this.images.length} изображений`);
                }
            }
            
        } catch (e) {
            console.error('❌ Ошибка восстановления сессии:', e);
        }
    }
    
    // Очистка старых данных
    async clearOldData() {
        if (!this.db) return;
        
        try {
            const oneHourAgo = Date.now() - 60 * 60 * 1000;
            
            const transaction = this.db.transaction(['images'], 'readwrite');
            const store = transaction.objectStore('images');
            const images = await new Promise((resolve) => {
                const request = store.getAll();
                request.onsuccess = () => resolve(request.result);
            });
            
            for (const img of images) {
                if (img.timestamp < oneHourAgo) {
                    store.delete(img.id);
                }
            }
            
            console.log('🧹 Старые данные очищены');
        } catch (e) {
            console.error('❌ Ошибка очистки данных:', e);
        }
    }
    
    initializeElements() {
        this.elements = {
            singleUpload: document.getElementById('single-upload'),
            folderUpload: document.getElementById('folder-upload'),
            singleImageRadio: document.getElementById('single-image'),
            multipleImagesRadio: document.getElementById('multiple-images'),
            toolType: document.getElementById('tool-type'),
            annotationColor: document.getElementById('annotation-color'),
            bgColor: document.getElementById('bg-color'),
            saveCropped: document.getElementById('save-cropped'),
            zoomIn: document.getElementById('zoom-in'),
            zoomOut: document.getElementById('zoom-out'),
            zoomReset: document.getElementById('zoom-reset'),
            zoomLevel: document.getElementById('zoom-level'),
            clearAnnotation: document.getElementById('clear-annotation'),
            nextImage: document.getElementById('next-image'),
            saveAnnotation: document.getElementById('save-annotation'),
            exportAll: document.getElementById('export-all'),
            testCoords: document.getElementById('test-coords'),
            currentFileName: document.getElementById('current-file-name'),
            annotationX: document.getElementById('annotation-x'),
            annotationY: document.getElementById('annotation-y'),
            annotationWidth: document.getElementById('annotation-width'),
            annotationHeight: document.getElementById('annotation-height'),
            processedCount: document.getElementById('processed-count'),
            totalCount: document.getElementById('total-count'),
            progressBar: document.getElementById('progress-bar'),
            progressInfo: document.querySelector('.progress-info'),
            canvasContainer: document.querySelector('.canvas-container')
        };

        this.elements.bgColor.value = '#00ff00';
        this.fillColor = 'rgba(0, 255, 0, 0.3)';
    }
    
    setupEventListeners() {
        // Загрузка изображений
        this.elements.singleUpload.addEventListener('change', (e) => this.loadSingleImage(e));
        this.elements.folderUpload.addEventListener('change', (e) => this.loadFolderImages(e));
        
        // Переключение режимов
        this.elements.singleImageRadio.addEventListener('change', () => {
            this.elements.singleUpload.style.display = 'block';
            this.elements.folderUpload.style.display = 'none';
            this.elements.nextImage.style.display = 'none';
            if (this.elements.progressInfo) this.elements.progressInfo.style.display = 'none';
            this.saveSession();
        });
        
        this.elements.multipleImagesRadio.addEventListener('change', () => {
            this.elements.singleUpload.style.display = 'none';
            this.elements.folderUpload.style.display = 'block';
            this.elements.nextImage.style.display = 'block';
            this.saveSession();
        });
        
        // Инструменты
        this.elements.toolType.addEventListener('change', (e) => {
            this.tool = e.target.value;
            this.saveSession();
        });
        
        this.elements.annotationColor.addEventListener('input', (e) => {
            this.strokeColor = e.target.value;
            this.draw();
            this.saveSession();
        });
        
        this.elements.bgColor.addEventListener('input', (e) => {
            this.fillColor = this.hexToRgba(e.target.value, 0.3);
            this.draw();
            this.saveSession();
        });
        
        // Масштаб
        this.elements.zoomIn.addEventListener('click', (e) => {
            e.preventDefault();
            this.zoomIn();
        });
        
        this.elements.zoomOut.addEventListener('click', (e) => {
            e.preventDefault();
            this.zoomOut();
        });
        
        this.elements.zoomReset.addEventListener('click', (e) => {
            e.preventDefault();
            this.resetZoom();
        });
        
        // Управление
        this.elements.clearAnnotation.addEventListener('click', () => this.clearAnnotation());
        this.elements.nextImage.addEventListener('click', () => this.nextImage());
        this.elements.saveAnnotation.addEventListener('click', () => this.saveCurrentAnnotation());
        this.elements.exportAll.addEventListener('click', () => this.exportAllAnnotations());
        this.elements.testCoords.addEventListener('click', () => this.testCoordinates());
        
        // События мыши
        this.canvas.addEventListener('mousedown', this.onMouseDown.bind(this));
        this.canvas.addEventListener('mousemove', this.onMouseMove.bind(this));
        this.canvas.addEventListener('mouseup', this.onMouseUp.bind(this));
        this.canvas.addEventListener('wheel', this.onWheel.bind(this), { passive: false });
        
        this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
        
        window.addEventListener('resize', () => {
            if (this.currentImage) {
                this.updateCanvasSize();
                this.draw();
            }
        });

        window.addEventListener('beforeunload', () => {
            this.saveSession();
        });
    }
    
    zoomIn() {
        const newScale = this.scale + this.scaleStep;
        if (newScale <= this.maxScale) {
            this.scale = newScale;
            this.updateZoomDisplay();
            this.draw();
        }
    }
    
    zoomOut() {
        const newScale = this.scale - this.scaleStep;
        if (newScale >= this.minScale) {
            this.scale = newScale;
            this.updateZoomDisplay();
            this.draw();
        }
    }
    
    resetZoom() {
        this.scale = 1;
        this.updateZoomDisplay();
        this.draw();
    }
    
    updateZoomDisplay() {
        this.elements.zoomLevel.textContent = `${Math.round(this.scale * 100)}%`;
    }
    
    async saveFileWithPicker(content, defaultFileName, mimeType) {
        try {
            if (!window.showSaveFilePicker) {
                const blob = new Blob([content], { type: mimeType });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = defaultFileName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                alert(`📁 Файл сохранен как "${defaultFileName}" в папку "Загрузки"`);
                return;
            }
            
            const opts = {
                suggestedName: defaultFileName,
                types: [{
                    description: mimeType.includes('json') ? 'JSON файл' : 'PNG изображение',
                    accept: {
                        [mimeType]: [mimeType.includes('json') ? '.json' : '.png']
                    }
                }]
            };
            
            const handle = await window.showSaveFilePicker(opts);
            const writable = await handle.createWritable();
            await writable.write(content);
            await writable.close();
            
            alert(`✅ Файл сохранен: ${handle.name}`);
            
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('❌ Ошибка сохранения:', err);
                alert('❌ Не удалось сохранить файл');
            }
        }
    }
    
    async saveImageWithPicker(dataURL, defaultFileName) {
        try {
            const blob = await (await fetch(dataURL)).blob();
            await this.saveFileWithPicker(blob, defaultFileName, 'image/png');
        } catch (error) {
            console.error('❌ Ошибка сохранения изображения:', error);
        }
    }
    
    // ИСПРАВЛЕННЫЙ метод получения координат
    getImageCoords(e) {
        const rect = this.canvas.getBoundingClientRect();
        
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        const unzoomedX = mouseX / this.scale;
        const unzoomedY = mouseY / this.scale;
        
        const imageX = (unzoomedX / this.displayWidth) * this.imageWidth;
        const imageY = (unzoomedY / this.displayHeight) * this.imageHeight;
        
        const boundedX = Math.max(0, Math.min(imageX, this.imageWidth));
        const boundedY = Math.max(0, Math.min(imageY, this.imageHeight));
        
        return {
            x: boundedX,
            y: boundedY
        };
    }
    
    updateCanvasSize() {
        if (!this.elements.canvasContainer || !this.currentImage) return;
        
        const container = this.elements.canvasContainer;
        const maxWidth = container.clientWidth - 4;
        const maxHeight = container.clientHeight - 4;
        
        let displayWidth = this.imageWidth;
        let displayHeight = this.imageHeight;
        
        if (displayWidth > maxWidth || displayHeight > maxHeight) {
            const widthRatio = maxWidth / displayWidth;
            const heightRatio = maxHeight / displayHeight;
            const ratio = Math.min(widthRatio, heightRatio);
            
            displayWidth = Math.floor(displayWidth * ratio);
            displayHeight = Math.floor(displayHeight * ratio);
        }
        
        this.canvas.width = displayWidth;
        this.canvas.height = displayHeight;
        
        this.displayWidth = displayWidth;
        this.displayHeight = displayHeight;
        this.displayRatio = displayWidth / this.imageWidth;
    }
    
    hexToRgba(hex, alpha = 1) {
        hex = hex.replace('#', '');
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    
    async loadSingleImage(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        await this.clearOldData();
        
        const id = await this.saveImageToDB(file);
        
        this.images = [{
            id: id,
            file: file,
            name: file.name,
            url: URL.createObjectURL(file),
            annotation: null
        }];
        
        this.currentImageIndex = 0;
        await this.displayCurrentImage();
        this.updateUI();
        this.saveSession();
    }
    
    async loadFolderImages(event) {
        const files = Array.from(event.target.files).filter(file => 
            file.type.startsWith('image/')
        );
        
        if (files.length === 0) return;
        
        await this.clearOldData();
        
        this.images = [];
        for (const file of files) {
            const id = await this.saveImageToDB(file);
            this.images.push({
                id: id,
                file: file,
                name: file.name,
                url: URL.createObjectURL(file),
                annotation: null,
                webkitRelativePath: file.webkitRelativePath
            });
        }
        
        this.currentImageIndex = 0;
        
        if (this.elements.progressInfo) {
            this.elements.progressInfo.style.display = 'block';
            this.elements.totalCount.textContent = this.images.length;
            this.elements.processedCount.textContent = '1';
            this.elements.progressBar.value = (1 / this.images.length) * 100;
        }
        
        await this.displayCurrentImage();
        this.updateUI();
        this.saveSession();
    }
    
    async displayCurrentImage() {
        if (this.images.length === 0) return;
        
        const imageData = this.images[this.currentImageIndex];
        this.elements.currentFileName.textContent = imageData.name;
        
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                this.currentImage = img;
                this.imageWidth = img.naturalWidth || img.width;
                this.imageHeight = img.naturalHeight || img.height;
                
                this.updateCanvasSize();
                this.scale = 1;
                this.updateZoomDisplay();
                this.draw();
                resolve();
            };
            
            img.onerror = () => {
                alert(`Ошибка загрузки: ${imageData.name}`);
                resolve();
            };
            
            img.src = imageData.url;
        });
    }
    
    // ИСПРАВЛЕННЫЙ метод отрисовки
    draw() {
        if (!this.currentImage) return;
        
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.save();
        
        this.ctx.scale(this.scale, this.scale);
        
        this.ctx.drawImage(
            this.currentImage,
            0, 0, this.imageWidth, this.imageHeight,
            0, 0, this.displayWidth, this.displayHeight
        );
        
        this.drawAnnotations();
        
        this.ctx.restore();
    }
    
    drawAnnotations() {
        const savedAnnotation = this.images[this.currentImageIndex]?.annotation;
        if (savedAnnotation) {
            this.drawSingleAnnotation(savedAnnotation);
        }
        
        if (this.currentAnnotation) {
            this.drawSingleAnnotation(this.currentAnnotation);
        }
    }
    
    drawSingleAnnotation(annotation) {
        this.ctx.save();
        
        const { x, y, width, height, type } = annotation;
        
        const displayX = (x / this.imageWidth) * this.displayWidth;
        const displayY = (y / this.imageHeight) * this.displayHeight;
        const displayW = (Math.abs(width) / this.imageWidth) * this.displayWidth;
        const displayH = (Math.abs(height) / this.imageHeight) * this.displayHeight;
        
        this.ctx.strokeStyle = this.strokeColor;
        this.ctx.fillStyle = this.fillColor;
        this.ctx.lineWidth = 2;
        
        switch(type) {
            case 'rectangle':
                this.ctx.fillRect(displayX, displayY, displayW, displayH);
                this.ctx.strokeRect(displayX, displayY, displayW, displayH);
                break;
                
            case 'circle':
                const centerX = displayX + displayW / 2;
                const centerY = displayY + displayH / 2;
                const radius = Math.min(displayW, displayH) / 2;
                
                this.ctx.beginPath();
                this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.stroke();
                break;
                
            case 'freehand':
                if (annotation.points && annotation.points.length > 1) {
                    this.ctx.beginPath();
                    
                    const firstPoint = annotation.points[0];
                    const firstX = (firstPoint.x / this.imageWidth) * this.displayWidth;
                    const firstY = (firstPoint.y / this.imageHeight) * this.displayHeight;
                    this.ctx.moveTo(firstX, firstY);
                    
                    for (let i = 1; i < annotation.points.length; i++) {
                        const point = annotation.points[i];
                        const pointX = (point.x / this.imageWidth) * this.displayWidth;
                        const pointY = (point.y / this.imageHeight) * this.displayHeight;
                        this.ctx.lineTo(pointX, pointY);
                    }
                    
                    if (annotation.points.length > 2) {
                        this.ctx.closePath();
                    }
                    
                    this.ctx.fill();
                    this.ctx.stroke();
                }
                break;
        }
        
        this.ctx.restore();
    }
    
    onMouseDown(e) {
        if (!this.currentImage) return;
        
        e.preventDefault();
        
        const imagePos = this.getImageCoords(e);
        
        this.isDrawing = true;
        this.startX = imagePos.x;
        this.startY = imagePos.y;
        
        if (this.tool === 'freehand') {
            this.currentAnnotation = {
                type: 'freehand',
                points: [{ x: imagePos.x, y: imagePos.y }],
                x: imagePos.x,
                y: imagePos.y,
                width: 0,
                height: 0
            };
        } else if (this.tool === 'circle') {
            this.currentAnnotation = {
                type: 'circle',
                x: imagePos.x,
                y: imagePos.y,
                width: 0,
                height: 0
            };
        } else {
            this.currentAnnotation = {
                type: 'rectangle',
                x: imagePos.x,
                y: imagePos.y,
                width: 0,
                height: 0
            };
        }
        
        this.draw();
    }
    
    onMouseMove(e) {
        if (!this.isDrawing || !this.currentAnnotation) return;
        
        e.preventDefault();
        
        const currentPos = this.getImageCoords(e);
        
        if (this.tool === 'freehand') {
            this.currentAnnotation.points.push({ x: currentPos.x, y: currentPos.y });
            
            const points = this.currentAnnotation.points;
            const xs = points.map(p => p.x);
            const ys = points.map(p => p.y);
            this.currentAnnotation.x = Math.min(...xs);
            this.currentAnnotation.y = Math.min(...ys);
            this.currentAnnotation.width = Math.max(...xs) - this.currentAnnotation.x;
            this.currentAnnotation.height = Math.max(...ys) - this.currentAnnotation.y;
        } else {
            this.currentAnnotation.width = currentPos.x - this.startX;
            this.currentAnnotation.height = currentPos.y - this.startY;
        }
        
        this.updateAnnotationInfo(this.currentAnnotation);
        this.draw();
    }
    
    async onMouseUp(e) {
        if (!this.isDrawing || !this.currentAnnotation) return;
        
        e.preventDefault();
        this.isDrawing = false;
        
        let annotation = { ...this.currentAnnotation };
        
        if (this.tool === 'rectangle') {
            let x = annotation.x;
            let y = annotation.y;
            let width = annotation.width;
            let height = annotation.height;
            
            if (width < 0) {
                x += width;
                width = Math.abs(width);
            }
            if (height < 0) {
                y += height;
                height = Math.abs(height);
            }
            
            annotation.x = Math.max(0, Math.min(x, this.imageWidth));
            annotation.y = Math.max(0, Math.min(y, this.imageHeight));
            annotation.width = Math.min(width, this.imageWidth - annotation.x);
            annotation.height = Math.min(height, this.imageHeight - annotation.y);
        } else if (this.tool === 'circle') {
            let x = annotation.x;
            let y = annotation.y;
            let width = Math.abs(annotation.width);
            let height = Math.abs(annotation.height);
            
            if (annotation.width < 0) x -= width;
            if (annotation.height < 0) y -= height;
            
            annotation.x = Math.max(0, Math.min(x, this.imageWidth));
            annotation.y = Math.max(0, Math.min(y, this.imageHeight));
            annotation.width = Math.min(width, this.imageWidth - annotation.x);
            annotation.height = Math.min(height, this.imageHeight - annotation.y);
        }
        
        if (Math.abs(annotation.width) < 5 || Math.abs(annotation.height) < 5) {
            this.currentAnnotation = null;
            this.draw();
            return;
        }
        
        this.images[this.currentImageIndex].annotation = annotation;
        
        await this.updateAnnotationInDB(this.images[this.currentImageIndex].id, annotation);
        
        this.currentAnnotation = null;
        this.draw();
        this.updateUI();
        this.saveSession();
    }
    
    onWheel(e) {
        e.preventDefault();
        
        if (e.deltaY < 0) {
            this.zoomIn();
        } else {
            this.zoomOut();
        }
    }
    
    updateAnnotationInfo(annotation) {
        if (!annotation) {
            this.elements.annotationX.textContent = '0';
            this.elements.annotationY.textContent = '0';
            this.elements.annotationWidth.textContent = '0';
            this.elements.annotationHeight.textContent = '0';
            return;
        }
        
        this.elements.annotationX.textContent = Math.round(annotation.x);
        this.elements.annotationY.textContent = Math.round(annotation.y);
        this.elements.annotationWidth.textContent = Math.round(Math.abs(annotation.width));
        this.elements.annotationHeight.textContent = Math.round(Math.abs(annotation.height));
    }
    
    async clearAnnotation() {
        if (this.images.length === 0) return;
        
        this.images[this.currentImageIndex].annotation = null;
        
        await this.updateAnnotationInDB(this.images[this.currentImageIndex].id, null);
        
        this.currentAnnotation = null;
        this.updateAnnotationInfo(null);
        this.draw();
        this.saveSession();
    }
    
    createMaskImage(annotation) {
        if (!annotation || annotation.type !== 'freehand') return null;
        
        const maskCanvas = document.createElement('canvas');
        maskCanvas.width = this.imageWidth;
        maskCanvas.height = this.imageHeight;
        const maskCtx = maskCanvas.getContext('2d');
        
        maskCtx.fillStyle = '#000000';
        maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
        
        maskCtx.fillStyle = '#FFFFFF';
        maskCtx.strokeStyle = '#FFFFFF';
        
        if (annotation.points && annotation.points.length > 1) {
            maskCtx.beginPath();
            maskCtx.moveTo(annotation.points[0].x, annotation.points[0].y);
            
            for (let i = 1; i < annotation.points.length; i++) {
                maskCtx.lineTo(annotation.points[i].x, annotation.points[i].y);
            }
            
            if (annotation.points.length > 2) {
                maskCtx.closePath();
            }
            
            maskCtx.fill();
        }
        
        return maskCanvas;
    }
    
    async saveCurrentAnnotation() {
        const currentImage = this.images[this.currentImageIndex];
        if (!currentImage || !currentImage.annotation) {
            alert('⚠️ Нет разметки для сохранения');
            return null;
        }
        
        const annotation = currentImage.annotation;
        const baseName = currentImage.name.replace(/\.[^/.]+$/, "");
        
        if (annotation.type === 'freehand' && this.elements.saveCropped.checked) {
            const maskCanvas = this.createMaskImage(annotation);
            if (maskCanvas) {
                const maskDataURL = maskCanvas.toDataURL('image/png');
                await this.saveImageWithPicker(maskDataURL, `${baseName}_mask.png`);
            }
        }
        
        if (this.elements.saveCropped.checked && annotation.type !== 'freehand') {
            await this.createCroppedImage(currentImage, annotation);
        }
        
        const annotationData = {
            imagePath: currentImage.name,
            timestamp: new Date().toISOString(),
            tool: annotation.type,
            coordinates: {
                x: Math.round(annotation.x),
                y: Math.round(annotation.y),
                width: Math.round(Math.abs(annotation.width)),
                height: Math.round(Math.abs(annotation.height))
            },
            originalImageSize: {
                width: this.imageWidth,
                height: this.imageHeight
            },
            points: annotation.type === 'freehand' ? annotation.points : null
        };
        
        const json = JSON.stringify(annotationData, null, 2);
        await this.saveFileWithPicker(json, `${baseName}_annotation.json`, 'application/json');
        
        return annotationData;
    }
    
    async nextImage() {
        if (this.images.length <= 1) {
            alert('Только одно изображение загружено');
            return;
        }
        
        if (this.currentImageIndex < this.images.length - 1) {
            this.currentImageIndex++;
        } else {
            this.currentImageIndex = 0;
        }
        
        if (this.elements.progressInfo) {
            this.elements.processedCount.textContent = this.currentImageIndex + 1;
            this.elements.progressBar.value = ((this.currentImageIndex + 1) / this.images.length) * 100;
        }
        
        await this.displayCurrentImage();
        this.updateUI();
        this.saveSession();
    }
    
    async createCroppedImage(imageData, annotation) {
        const img = new Image();
        
        return new Promise((resolve) => {
            img.onload = async () => {
                try {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    
                    let x = Math.round(annotation.x);
                    let y = Math.round(annotation.y);
                    let width = Math.round(Math.abs(annotation.width));
                    let height = Math.round(Math.abs(annotation.height));
                    
                    x = Math.max(0, Math.min(x, this.imageWidth));
                    y = Math.max(0, Math.min(y, this.imageHeight));
                    width = Math.min(width, this.imageWidth - x);
                    height = Math.min(height, this.imageHeight - y);
                    
                    if (width <= 0 || height <= 0) {
                        console.log('⚠️ Область слишком мала для обрезки');
                        resolve();
                        return;
                    }
                    
                    canvas.width = width;
                    canvas.height = height;
                    
                    ctx.drawImage(
                        img,
                        x, y, width, height,
                        0, 0, width, height
                    );
                    
                    const baseName = imageData.name.replace(/\.[^/.]+$/, "");
                    const dataURL = canvas.toDataURL('image/png');
                    await this.saveImageWithPicker(dataURL, `${baseName}_cropped.png`);
                    
                } catch (error) {
                    console.error('❌ Ошибка обрезки:', error);
                }
                resolve();
            };
            
            img.src = imageData.url;
        });
    }
    
    async exportAllAnnotations() {
        const allAnnotations = this.images
            .filter(img => img.annotation)
            .map(img => ({
                imagePath: img.name,
                annotation: img.annotation,
                timestamp: new Date().toISOString()
            }));
        
        if (allAnnotations.length === 0) {
            alert('⚠️ Нет разметок для экспорта');
            return;
        }
        
        const json = JSON.stringify({
            exportDate: new Date().toISOString(),
            totalImages: this.images.length,
            totalAnnotations: allAnnotations.length,
            annotations: allAnnotations
        }, null, 2);
        
        await this.saveFileWithPicker(json, 'all_annotations.json', 'application/json');
    }
    
    updateUI() {
        if (this.images.length === 0) return;
        
        const annotation = this.images[this.currentImageIndex]?.annotation;
        this.updateAnnotationInfo(annotation || null);
        
        if (this.elements.multipleImagesRadio.checked && this.elements.progressInfo) {
            this.elements.progressInfo.style.display = 'block';
            this.elements.totalCount.textContent = this.images.length;
            this.elements.processedCount.textContent = this.currentImageIndex + 1;
            this.elements.progressBar.value = ((this.currentImageIndex + 1) / this.images.length) * 100;
        }
    }
    
    testCoordinates() {
        if (!this.currentImage) {
            alert('Сначала загрузите изображение');
            return;
        }
        
        alert(`=== ТЕСТ КООРДИНАТ ===
        
Размер канваса (CSS):
width: ${this.canvas.clientWidth}px
height: ${this.canvas.clientHeight}px

Размер канваса (атрибуты):
width: ${this.canvas.width}px
height: ${this.canvas.height}px

Масштаб: ${this.scale}x (${Math.round(this.scale * 100)}%)

Реальные размеры отображения:
width: ${this.displayWidth}px
height: ${this.displayHeight}px

Размер изображения:
width: ${this.imageWidth}px
height: ${this.imageHeight}px

Коэффициент преобразования:
1 пиксель на канвасе = ${(this.imageWidth / this.displayWidth).toFixed(2)} пикселей изображения
`);
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.annotationTool = new ImageAnnotationTool();
        console.log('✅ Инструмент разметки готов к работе!');
    } catch (error) {
        console.error('❌ Ошибка инициализации:', error);
        alert('❌ Ошибка загрузки инструмента. Откройте консоль (F12) для деталей.');
    }
});