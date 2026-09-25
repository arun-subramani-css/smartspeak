import React, { useState, useRef } from 'react';
import { Upload, FileVideo, AlertCircle, Shield, Film, Waves, CheckCircle2, X, Loader2, ArrowRight, Video } from 'lucide-react';
import { PracticeRecorder } from './PracticeRecorder';

const MAX_SIZE_MB = 500;
const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.webm'];

export function VideoUploader({ onUploadSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [mode, setMode] = useState('upload'); // 'upload' | 'practice'
  const fileInputRef = useRef(null);

  const validateFile = (file) => {
    if (!file) return 'No file selected.';

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file format '${ext}'. Please upload an .MP4, .AVI, .MOV, or .WEBM video file.`;
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

  const handleUpload = (fileOverride) => {
    const fileToUpload = fileOverride || selectedFile;
    if (!fileToUpload) return;

    const validationError = validateFile(fileToUpload);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setErrorMessage('');

    const formData = new FormData();
    formData.append('video', fileToUpload);

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
          setErrorMessage(`Upload failed with status code ${xhr.status}`);
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
      {/* Error Message — shown at top so it's never missed */}
      {errorMessage && (
        <div role="alert" style={{
          margin: '16px 16px 0',
          padding: '12px 16px',
          background: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: 'var(--radius-md)',
          color: '#dc2626',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
          fontSize: '0.875rem'
        }}>
          <AlertCircle size={18} style={{ flexShrink: 0, marginTop: '1px' }} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Header Row */}
      <div className="pro-card-header">
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Video Ingestion
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '2px' }}>
            Automated extraction & sampling pipeline
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="badge-pill">MAX 500 MB</span>
          <span className="badge-pill">.MP4 / .AVI / .MOV / .WEBM</span>
        </div>
      </div>

      <div className="pro-card-body">
        {/* Mode toggle */}
        {!selectedFile && !isUploading && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => setMode('upload')}
              aria-pressed={mode === 'upload'}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '7px 16px', borderRadius: 999, fontSize: '0.82rem', fontWeight: 700,
                cursor: 'pointer', transition: 'all 0.15s ease',
                border: `1px solid ${mode === 'upload' ? 'var(--primary-purple)' : 'var(--border-subtle)'}`,
                background: mode === 'upload' ? 'var(--primary-purple-light)' : '#ffffff',
                color: mode === 'upload' ? 'var(--primary-purple)' : 'var(--text-muted)',
              }}
            >
              <Upload size={14} />
              Upload a file
            </button>
            <button
              type="button"
              onClick={() => setMode('practice')}
              aria-pressed={mode === 'practice'}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '7px 16px', borderRadius: 999, fontSize: '0.82rem', fontWeight: 700,
                cursor: 'pointer', transition: 'all 0.15s ease',
                border: `1px solid ${mode === 'practice' ? 'var(--primary-purple)' : 'var(--border-subtle)'}`,
                background: mode === 'practice' ? 'var(--primary-purple-light)' : '#ffffff',
                color: mode === 'practice' ? 'var(--primary-purple)' : 'var(--text-muted)',
              }}
            >
              <Video size={14} />
              Practice now
            </button>
          </div>
        )}

        {/* Hidden File Input */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".mp4,.avi,.mov,.webm"
          style={{ display: 'none' }}
        />

        {/* Practice Mode — record in browser, then reuse the exact upload flow */}
        {mode === 'practice' && !selectedFile && (
          <PracticeRecorder
            onRecordingReady={(file) => {
              setMode('upload');
              setSelectedFile(file);
              setErrorMessage('');
              handleUpload(file); // straight into the existing flow
            }}
            onCancel={() => setMode('upload')}
          />
        )}

        {/* Dropzone */}
        {mode === 'upload' && !selectedFile && (
          <div
            className={`exact-dropzone ${dragActive ? 'active' : ''}`}
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="Upload a video recording: drag and drop here, or press Enter to browse files"
          >
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'var(--primary-purple-light)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              color: 'var(--primary-purple)'
            }}>
              <Upload size={26} />
            </div>

            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Drag and drop video recording here
            </h3>

            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
              or <span style={{ color: 'var(--primary-purple)', fontWeight: 700, textDecoration: 'underline', textUnderlineOffset: '3px' }}>browse files</span> to select manually
            </p>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '14px' }}>
              Tip: frame yourself from the waist up, with good lighting and minimal background noise, for the most accurate analysis.
            </p>
          </div>
        )}

        {/* Selected file card (both modes — practice sets the recorded file here too) */}
        {selectedFile && (
          <div style={{
            background: 'var(--bg-subtle)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '20px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <div style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '10px',
                  background: 'var(--primary-purple-light)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--primary-purple)'
                }}>
                  <FileVideo size={22} />
                </div>
                <div>
                  <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {selectedFile.name}
                  </h4>
                  <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • {selectedFile.type || 'video'}
                  </p>
                </div>
              </div>

              {!isUploading && (
                <button onClick={clearSelection} className="btn-light">
                  <X size={16} />
                  <span>Remove</span>
                </button>
              )}
            </div>

            {/* Upload Progress */}
            {isUploading && (
              <div style={{ marginTop: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Loader2 size={16} className="animate-spin" color="var(--primary-purple)" />
                    Uploading video stream...
                  </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{uploadProgress}%</strong>
                </div>
                <div className="pro-progress-bg">
                  <div className="pro-progress-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* CTA — stable so it never flashes */}
        <button
          className="btn-purple"
          onClick={() => handleUpload()}
          disabled={!selectedFile || isUploading}
          style={{ width: '100%', padding: '14px', marginTop: '20px' }}
        >
          {isUploading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>Uploading…</span>
            </>
          ) : (
            <>
              <span>Start Analysis</span>
              <ArrowRight size={18} />
            </>
          )}
        </button>

        {/* 3 Info Boxes at Card Bottom */}
        <div style={{ display: 'flex', gap: '16px', marginTop: '20px' }}>
          <div className="info-box">
            <div className="info-box-icon">
              <Shield size={20} />
            </div>
            <div>
              <div className="info-box-title">Validated</div>
              <div className="info-box-sub">Security scanning</div>
            </div>
          </div>

          <div className="info-box">
            <div className="info-box-icon">
              <Film size={20} />
            </div>
            <div>
              <div className="info-box-title">1 FPS Sampling</div>
              <div className="info-box-sub">Posture analysis</div>
            </div>
          </div>

          <div className="info-box">
            <div className="info-box-icon">
              <Waves size={20} />
            </div>
            <div>
              <div className="info-box-title">16kHz Mono</div>
              <div className="info-box-sub">Whisper audio</div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
