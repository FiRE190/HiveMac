import Foundation
import Carbon.HIToolbox

/// The global stop key, registered as a Carbon hot key. It works in any app and needs no
/// permission, and it can be re-registered live when the user picks another key.
public final class StopHotKey {
    private var ref: EventHotKeyRef?
    private var handler: EventHandlerRef?
    public var onPress: () -> Void = {}
    public private(set) var keyCode: UInt32?
    private static weak var current: StopHotKey?

    public init() {}

    deinit { unregister(); if let handler { RemoveEventHandler(handler) } }

    /// Registers `keyCode` (a macOS virtual key code) with no modifiers. Returns false if macOS refused.
    @discardableResult
    public func register(keyCode: UInt32) -> Bool {
        unregister()
        installHandlerOnce()
        let id = EventHotKeyID(signature: OSType(0x4856_4D43), id: 1)       // 'HVMC'
        var newRef: EventHotKeyRef?
        let status = RegisterEventHotKey(keyCode, 0, id, GetApplicationEventTarget(), 0, &newRef)
        guard status == noErr, let newRef else { return false }
        ref = newRef
        self.keyCode = keyCode
        StopHotKey.current = self
        return true
    }

    public func unregister() {
        if let ref { UnregisterEventHotKey(ref) }
        ref = nil
        keyCode = nil
    }

    private func installHandlerOnce() {
        guard handler == nil else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            DispatchQueue.main.async { StopHotKey.current?.onPress() }
            return noErr
        }, 1, &spec, nil, &handler)
    }
}
