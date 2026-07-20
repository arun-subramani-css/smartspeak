import React, { useState, useRef } from 'react';
import { UploadCloud, FileVideo, AlertCircle, ShieldCheck, Film, CheckCircle2, X, Loader2, ArrowRight } from 'lucide-react';

const MAX_SIZE_MB = 500;
const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov'];

export function VideoUploader({ onUploadSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const validateFile = (file) => {
    if (!file) return 'No file selected.';

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file format '${ext}'. Please upload an .MP4, .AVI, or .MOV video file.`;
    }

    const sizeMB = file.size / (1024 * 1024);
    if (sizeMB > MAX_SIZE_MB) {
      return `File size (${sizeMB.toFixed(1)} MB) exceeds maximum allowed limit of ${MAX_SIZE_MB} MB.`;
    }

    return null;
  };

  const handleFileChange = (e) => {
    setErrorMessage('');
    const file = e.target.files[0];
    if (file) {
      const err = validateFile(file);
      if (err) {
        setErrorMessage(err);
        setSelectedFile(null);
      } else {
        setSelectedFile(file);
      }
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    setErrorMessage('');

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const err = validateFile(file);
      if (err) {
        setErrorMessage(err);
        setSelectedFile(null);
      } else {
        setSelectedFile(file);
      }
    }
  };

  const handleUpload = () => {
    if (!selectedFile) return;

    const validationError = validateFile(selectedFile);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setErrorMessage('');

    const formData = new FormData();
    formData.append('video', selectedFile);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/upload', true);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
      }
    };

    xhr.onload = () => {
      setIsUploading(false);
      if (xhr.status === 201 || xhr.status === 200) {
        try {
          const response = JSON.parse(xhr.responseText);
          if (onUploadSuccess) {
            onUploadSuccess(response.session_id);
          }
        } catch (e) {
          setErrorMessage('Upload completed, but server returned an invalid response.');
        }
      } else {
        try {
          const res = JSON.parse(xhr.responseText);
          setErrorMessage(res.detail || `Upload rejected (HTTP ${xhr.status})`);
        } catch (e) {
          setErrorMessage(`Upload failed with status code ${xhr.status}: ${xhr.statusText}`);
        }
      }
    };

    xhr.onerror = () => {
      setIsUploading(false);
      setErrorMessage('Network communication error. Please ensure the backend server is running.');
    };

    xhr.send(formData);
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setErrorMessage('');
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="pro-card">
      <div className="pro-card-header">
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#ffffff' }}>
            Presentation Video Ingestion
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Upload presentation recording for automated audio extraction and video frame sampling
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <span className="status-pill" style={{ background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
            Max 500 MB
          </span>
          <span className="status-pill" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--primary-400)', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
            .MP4 / .AVI / .MOV
          </span>
        </div>
      </div>

      <div className="pro-card-body">
        {/* Hidden File Input */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".mp4,.avi,.mov"
          style={{ display: 'none' }}
        />

        {/* Dropzone Area */}
        {!selectedFile ? (
          <div
            className={`pro-dropzone ${dragActive ? 'active' : ''}`}
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'rgba(99, 102, 241, 0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              color: 'var(--primary-400)',
              border: '1px solid rgba(99, 102, 241, 0.3)'
            }}>
              <UploadCloud size={28} />
            </div>
            
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Drag & drop video recording here, or <span style={{ color: 'var(--primary-400)', textDecoration: 'underline', cursor: 'pointer' }}>browse files</span>
            </h3>

            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', maxWidth: '440px', margin: '0 auto 16px' }}>
              Automated container validation verifies MP4/AVI/MOV binary headers upon stream.
            </p>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <ShieldCheck size={14} color="var(--accent-emerald)" /> Container Validated
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Film size={14} color="var(--accent-cyan)" /> 1 FPS OpenCV Frame Sampling
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <CheckCircle2 size={14} color="var(--primary-400)" /> 16kHz Mono WAV Audio
              </span>
            </div>
          </div>
        ) : (
          <div style={{
            background: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '24px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  background: 'rgba(99, 102, 241, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--primary-400)',
                  border: '1px solid rgba(99, 102, 241, 0.3)'
                }}>
                  <FileVideo size={24} />
                </div>
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {selectedFile.name}
                  </h4>
                  <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • {selectedFile.type || 'video'}
                  </p>
                </div>
              </div>

              {!isUploading && (
                <button
                  onClick={clearSelection}
                  className="btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                >
                  <X size={16} />
                  <span>Remove File</span>
                </button>
              )}
            </div>

            {/* Upload Progress Bar */}
            {isUploading && (
              <div style={{ marginTop: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '8px', color: 'var(--text-secondary)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Loader2 size={16} className="animate-spin" color="var(--primary-400)" />
                    Uploading stream to staging storage...
                  </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{uploadProgress}%</strong>
                </div>
                <div className="pro-progress-bg">
                  <div className="pro-progress-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}

            {/* Action CTA */}
            {!isUploading && (
              <button
                className="btn-primary"
                onClick={handleUpload}
                style={{ width: '100%', padding: '14px', marginTop: '16px' }}
              >
                <span>Initiate Preprocessing Pipeline</span>
                <ArrowRight size={18} />
              </button>
            )}
          </div>
        )}

        {/* Error Alert Banner */}
        {errorMessage && (
          <div style={{
            marginTop: '20px',
            padding: '14px 18px',
            background: 'var(--status-danger-bg)',
            border: '1px solid var(--status-danger-border)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--status-danger)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px',
            fontSize: '0.875rem'
          }}>
            <AlertCircle size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong style={{ display: 'block', fontWeight: 600, marginBottom: '2px' }}>Upload Error</strong>
              <span>{errorMessage}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
