import SwiftUI

/// The one primary action: honey fill, dark text.
struct HoneyButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.bodyStrong)
            .foregroundStyle(Theme.onHoney)
            .padding(.horizontal, Theme.s4)
            .frame(height: 36)
            .background(RoundedRectangle(cornerRadius: Theme.controlRadius).fill(Theme.honey.opacity(configuration.isPressed ? 0.8 : 1)))
            .opacity(enabled ? 1 : 0.4)
    }
}

/// Everything else: a raised plank with a hairline.
struct QuietButtonStyle: ButtonStyle {
    var tint: Color = Theme.wax
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.bodyStrong)
            .foregroundStyle(tint)
            .padding(.horizontal, Theme.s3)
            .frame(height: 32)
            .background(RoundedRectangle(cornerRadius: Theme.controlRadius).fill(Theme.plank.opacity(configuration.isPressed ? 0.7 : 1)))
            .overlay(RoundedRectangle(cornerRadius: Theme.controlRadius).stroke(Theme.grain, lineWidth: 1))
            .opacity(enabled ? 1 : 0.4)
    }
}

/// A key as it is drawn on the keyboard, for the stop key.
/// A label and its control on one aligned row.
struct SettingRow<Content: View>: View {
    var label: String
    var hint: String? = nil
    @ViewBuilder var content: Content
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.s4) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label).font(Theme.body).foregroundStyle(Theme.wax)
                if let hint { Text(hint).font(Theme.caption).foregroundStyle(Theme.dust).fixedSize(horizontal: false, vertical: true) }
            }
            .frame(width: 170, alignment: .leading)
            content
            Spacer(minLength: 0)
        }
        .frame(minHeight: Theme.rowHeight)
    }
}

struct SectionTitle: View {
    var text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(Theme.serif(15)).foregroundStyle(Theme.wax).padding(.top, Theme.s4).padding(.bottom, Theme.s1)
    }
}

extension View {
    /// Text field styled like the rest of the controls.
    func fieldStyle(width: CGFloat) -> some View {
        self.textFieldStyle(.plain)
            .font(Theme.figure)
            .foregroundStyle(Theme.wax)
            .multilineTextAlignment(.trailing)
            .padding(.horizontal, Theme.s2)
            .frame(width: width, height: 28)
            .background(RoundedRectangle(cornerRadius: 6).fill(Theme.plank))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.grain, lineWidth: 1))
    }
}

/// A compact drop-down in the app's own look (the system Picker draws a blue stepper).
struct Choice<T: Hashable>: View {
    var options: [(value: T, label: String)]
    @Binding var selection: T
    var width: CGFloat = 110
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        Menu {
            ForEach(options.indices, id: \.self) { i in
                Button(options[i].label) { selection = options[i].value }
            }
        } label: {
            HStack(spacing: Theme.s1) {
                Text(options.first { $0.value == selection }?.label ?? "").font(Theme.body).foregroundStyle(Theme.wax).lineLimit(1)
                Spacer(minLength: 0)
                Image(systemName: "chevron.down").font(.system(size: 9, weight: .bold)).foregroundStyle(Theme.dust)
            }
            .padding(.horizontal, Theme.s2)
            .frame(width: width, height: 28)
            .background(RoundedRectangle(cornerRadius: 6).fill(Theme.plank))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.grain, lineWidth: 1))
            .opacity(enabled ? 1 : 0.5)
        }
        .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden).fixedSize()
    }
}
