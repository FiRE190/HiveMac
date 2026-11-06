import SwiftUI
import AppKit

struct LogView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(model.log.enumerated()), id: \.offset) { i, line in
                            Text(line).font(.system(size: 12, design: .monospaced)).foregroundStyle(Theme.resin)
                                .frame(maxWidth: .infinity, alignment: .leading).id(i)
                        }
                    }
                    .padding(Theme.s4)
                }
                .onChange(of: model.log.count) { _, count in proxy.scrollTo(count - 1, anchor: .bottom) }
            }
            Divider().overlay(Theme.grain)
            HStack {
                Text("\(model.log.count) lines").font(Theme.caption).foregroundStyle(Theme.dust)
                Spacer()
                Button("Copy log") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(model.log.joined(separator: "\n"), forType: .string)
                }.buttonStyle(QuietButtonStyle())
            }
            .padding(Theme.s3)
        }
    }
}
