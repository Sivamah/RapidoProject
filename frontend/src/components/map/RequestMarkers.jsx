import React from 'react';
import { Marker, InfoWindow } from '@react-google-maps/api';
import MarkerPopup from './MarkerPopup';
import { requestTypeMeta } from '../../utils/requestSemantics';
import { googleQueueIcon } from './markerIcons';

/**
 * Background layer: pending requests from the live simulation queue.
 *
 * Type identity (colour + glyph) comes from `utils/requestSemantics`, the one
 * source of truth shared with the XAI highlight layer — previously this file
 * owned a private palette that painted food and parcel the same purple while
 * the highlight layer on the same map used a different scheme entirely.
 *
 * Markers are dimmed, not hidden, when a trip or XAI decision is in focus, so
 * the selected route stays the centre of attention without losing context.
 */
export default function RequestMarkers({
  requests = [],
  selectedRequest,
  onSelectRequest,
  onClosePopup,
  dimmed = false,
}) {
  return (
    <>
      {requests.map((req) => {
        if (!req.pickup_lat || !req.pickup_lng) return null;

        const meta = requestTypeMeta(req.request_type);
        const isSelected = req.id === selectedRequest?.id;
        const isDimmed = dimmed && !isSelected;

        return (
          <Marker
            key={req.id}
            position={{ lat: req.pickup_lat, lng: req.pickup_lng }}
            icon={googleQueueIcon(meta.color, meta.key, isDimmed, isSelected ? 34 : isDimmed ? 24 : 30)}
            zIndex={isSelected ? 20 : isDimmed ? 1 : 10}
            onClick={() => onSelectRequest(req)}
            title={`${meta.label} request #${req.id} — pickup: ${req.pickup_address || 'unknown'}`}
          />
        );
      })}

      {selectedRequest && selectedRequest.pickup_lat && selectedRequest.pickup_lng && (
        <InfoWindow
          position={{ lat: selectedRequest.pickup_lat, lng: selectedRequest.pickup_lng }}
          onCloseClick={onClosePopup}
        >
          <MarkerPopup request={selectedRequest} onClose={onClosePopup} />
        </InfoWindow>
      )}
    </>
  );
}
