import MapKit
import SwiftUI

struct RealtimeMapNoticeSketch: View {
    @State private var cameraPosition: MapCameraPosition = .region(
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 25.0173, longitude: 121.5397),
            span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
        )
    )

    var body: some View {
        ZStack(alignment: .bottom) {
            Map(position: $cameraPosition)
                .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 8) {
                Text("realtime_map_notice")
                    .font(.headline)
                Text("附近即時動態會出現在這裡")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .padding()
        }
    }
}

#Preview {
    RealtimeMapNoticeSketch()
}
